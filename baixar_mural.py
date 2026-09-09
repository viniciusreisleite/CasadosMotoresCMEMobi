import os, sys, json, time, re, shutil
import requests
from playwright.sync_api import sync_playwright
import yt_dlp

ACCOUNTS = [
    {"username": "cme.mobi", "badge": "Casa dos Motores", "color": "#e11d48"}
]

TARGET_TOTAL = 12
POSTS_PER_ACCOUNT = 12
DATA_JSON = "data.json"
COOKIES_FILE = "cookies.txt"

def carregar_cookies_playwright():
    if not os.path.exists(COOKIES_FILE):
        return []
    cookies = []
    with open(COOKIES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                domain, _, path, secure, expires, name, value = parts[:7]
                cookies.append({
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": path,
                    "secure": secure.lower() == "true",
                    "expires": float(expires) if expires.isdigit() else -1
                })
    return cookies

def extrair_shortcode(url):
    m = re.search(r'/(?:p|reel|tv)/([^/?#&]+)', url)
    return m.group(1) if m else url

def carregar_cache():
    if os.path.exists(DATA_JSON):
        try:
            with open(DATA_JSON, "r", encoding="utf-8") as f:
                dados = json.load(f)
                cache = {}
                for item in dados:
                    url = item.get("url") or item.get("link", "")
                    sc = extrair_shortcode(url)
                    if sc:
                        cache[sc] = item
                return cache
        except Exception:
            return {}
    return {}

def baixar_imagem_hd(url, destino):
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            with open(destino, "wb") as f:
                f.write(r.content)
            return True
    except Exception:
        pass
    return False

def processar_mural():
    cache_local = carregar_cache()
    posts_a_manter = []
    cookies_playwright = carregar_cookies_playwright()

    print("=== INICIANDO SINCRONIZACAO (SESSAO AUTENTICADA) ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        if cookies_playwright:
            context.add_cookies(cookies_playwright)

        page = context.new_page()

        for acc in ACCOUNTS:
            usr = acc["username"]
            badge = acc.get("badge", "")
            cor = acc.get("color", "#ff1744")
            print(f"\nChecando feed de @{usr}...")

            page.goto(f"https://www.instagram.com/{usr}/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
            urls_encontradas = []

            for _ in range(8):
                anchors = page.query_selector_all('a[href*="/p/"], a[href*="/reel/"]')
                for a in anchors:
                    href = a.get_attribute("href")
                    if href:
                        clean = href.split("?")[0].strip("/")
                        full = f"https://www.instagram.com/{clean}/"
                        if full not in urls_encontradas:
                            urls_encontradas.append(full)
                if len(urls_encontradas) >= POSTS_PER_ACCOUNT:
                    break
                page.evaluate("window.scrollBy(0, 1000)")
                page.wait_for_timeout(600)

            candidatos = urls_encontradas[:POSTS_PER_ACCOUNT]
            print(f"Posts no feed: {len(candidatos)} identificados.")

            for url in candidatos:
                sc = extrair_shortcode(url)

                if sc in cache_local:
                    item_cache = cache_local[sc]
                    arquivo_salvo = item_cache.get("arquivo")
                    if arquivo_salvo and os.path.exists(arquivo_salvo):
                        print(f"  [CACHE OK] {sc} ({arquivo_salvo})")
                        posts_a_manter.append(item_cache)
                        continue

                print(f"  [NOVO POST] Baixando: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1000)

                caption = ""
                meta_tag = page.query_selector('meta[property="og:title"]')
                if meta_tag:
                    caption = meta_tag.get_attribute("content") or ""

                post_temp_id = f"temp_{sc}"
                tipo = "image"
                arquivo_final = f"{post_temp_id}.jpg"

                video_elem = page.query_selector("article video, main video")
                if video_elem:
                    ydl_opts = {
                        'outtmpl': f'{post_temp_id}.%(ext)s',
                        'format': 'bestvideo+bestaudio/best',
                        'socket_timeout': 15,
                        'retries': 3,
                        'fragment_retries': 3,
                        'quiet': True
                    }
                    if os.path.exists(COOKIES_FILE):
                        ydl_opts['cookiefile'] = COOKIES_FILE
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            ydl.download([url])
                        for ext in [".mp4", ".mkv", ".webm"]:
                            if os.path.exists(f"{post_temp_id}{ext}"):
                                arquivo_final = f"{post_temp_id}{ext}"
                                tipo = "video"
                                break
                    except Exception:
                        tipo = "image"

                if tipo != "video":
                    img_url = None
                    meta_img = page.query_selector('meta[property="og:image"]')
                    if meta_img:
                        img_url = meta_img.get_attribute("content")

                    if not img_url:
                        img = page.query_selector('article img[srcset], main img[srcset]')
                        if img:
                            srcset = img.get_attribute("srcset")
                            if srcset:
                                cand_img = [s.strip().split(" ")[0] for s in srcset.split(",")]
                                img_url = cand_img[-1] if cand_img else None
                            if not img_url:
                                img_url = img.get_attribute("src")

                    if img_url:
                        baixar_imagem_hd(img_url, arquivo_final)

                if os.path.exists(arquivo_final):
                    posts_a_manter.append({
                        "id": sc,
                        "url": url,
                        "caption": caption,
                        "tipo": tipo,
                        "arquivo": arquivo_final,
                        "badge": badge,
                        "cor": cor,
                        "perfil": usr
                    })

        browser.close()

    if not posts_a_manter:
        print("\nNenhum post localizado. Mantendo arquivos locais intactos!")
        return

    posts_finais = posts_a_manter[:TARGET_TOTAL]
    dados_json_novo = []

    print("\nOrganizando arquivos de 1 a 12...")
    arquivos_preservados = set()

    for idx, item in enumerate(posts_finais, start=1):
        ext = os.path.splitext(item["arquivo"])[1]
        nome_slot = f"media_{idx}{ext}"

        origem = item["arquivo"]
        if origem != nome_slot:
            if os.path.exists(nome_slot):
                os.remove(nome_slot)
            shutil.move(origem, nome_slot)
            item["arquivo"] = nome_slot

        arquivos_preservados.add(nome_slot)
        dados_json_novo.append(item)

    for arq in os.listdir("."):
        if (arq.startswith("media_") or arq.startswith("temp_")) and (arq.endswith(".jpg") or arq.endswith(".mp4") or arq.endswith(".png")):
            if arq not in arquivos_preservados:
                try:
                    os.remove(arq)
                except Exception:
                    pass

    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(dados_json_novo, f, indent=2, ensure_ascii=False)

    print(f"Concluido! {len(dados_json_novo)} midias prontas e data.json atualizado.")

if __name__ == "__main__":
    processar_mural()