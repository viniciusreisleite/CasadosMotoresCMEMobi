import os
import sys
import time
import json
import requests
from playwright.sync_api import sync_playwright

PERFIS = ['cme.mobi']
PERFIL = 'cme.mobi'
BADGE_TEXTO = 'Casa dos Motores'
COR_TEMA = '#f97316'
TOTAL_MIDIAS = 12
COOKIES_FILE = "cookies.txt"

def carregar_cookies():
    cookies_dict = {}
    if os.path.exists(COOKIES_FILE):
        with open(COOKIES_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): continue
                p = line.split("\t")
                if len(p) >= 7:
                    cookies_dict[p[5]] = p[6]
    return cookies_dict

def shortcode_to_media_id(shortcode):
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    media_id = 0
    for letter in shortcode:
        media_id = (media_id * 64) + alphabet.index(letter)
    return str(media_id)

def baixar_midia_por_tipo(shortcode, out_prefix, cookies_dict):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "X-IG-App-ID": "936619743392459",
        "Accept": "*/*"
    }
    mid = shortcode_to_media_id(shortcode)
    api_url = f"https://www.instagram.com/api/v1/media/{mid}/info/"
    try:
        r = requests.get(api_url, headers=headers, cookies=cookies_dict, timeout=15)
        if r.status_code != 200:
            return None, None
        data = r.json()
        items = data.get("items", [])
        if not items: return None, None
        item = items[0]
        if item.get('timeline_pinned_user_ids') or item.get('is_pinned'):
            return 'pinned', None
        media_type = item.get("media_type")
        if media_type == 8:
            carousel = item.get("carousel_media", [])
            if not carousel: return None, None
            item = carousel[0]
            media_type = item.get("media_type")
        if media_type == 2:
            videos = item.get("video_versions", [])
            if videos:
                arquivo = f"{out_prefix}.mp4"
                res = requests.get(videos[0]["url"], timeout=30)
                if res.status_code == 200:
                    with open(arquivo, "wb") as f: f.write(res.content)
                    return "video", arquivo
        elif media_type == 1:
            cands = item.get("image_versions2", {}).get("candidates", [])
            if cands:
                arquivo = f"{out_prefix}.jpg"
                res = requests.get(cands[0]["url"], timeout=20)
                if res.status_code == 200:
                    with open(arquivo, "wb") as f: f.write(res.content)
                    return "image", arquivo
    except Exception:
        pass
    return None, None

def main():
    cookies_dict = carregar_cookies()
    cookies_playwright = [{"name": k, "value": v, "domain": ".instagram.com", "path": "/"} for k, v in cookies_dict.items()]
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        if cookies_playwright: ctx.add_cookies(cookies_playwright)
        page = ctx.new_page()
        
        urls = []
        for pf in PERFIS:
            print(f"\nChecando feed de @{pf}...")
            try:
                page.goto(f"https://www.instagram.com/{pf}/", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)
                for _ in range(25):
                    anchors = page.query_selector_all('a[href*="/p/"], a[href*="/reel/"]')
                    for a in anchors:
                        h = a.get_attribute("href")
                        if h:
                            caminho = h.split("?")[0].strip("/")
                            clean = f"https://www.instagram.com/{caminho}/"
                            if clean not in urls:
                                urls.append((clean, pf))
                    if len(urls) >= 15: break
                    page.evaluate("window.scrollBy(0, 1500)")
                    page.wait_for_timeout(1000)
            except Exception as e:
                print(f"Erro ao abrir perfil {pf}: {e}")
                
        posts_a_manter = []
        for url, post_perfil in urls:
            raw_sc = url.strip("/").split("/")[-1]
            sc = raw_sc[:11] if len(raw_sc) > 11 and "_" not in raw_sc else raw_sc
            out_prefix = f"temp_{sc}"
            
            caption = ""
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1000)
                meta_tag = page.query_selector('meta[property="og:title"]')
                if meta_tag: caption = meta_tag.get_attribute("content") or ""
            except Exception:
                pass

            tipo, arquivo = baixar_midia_por_tipo(sc, out_prefix, cookies_dict)
            if tipo == 'pinned':
                continue
            if arquivo and os.path.exists(arquivo):
                posts_a_manter.append({
                    "id": sc, "url": url, "caption": caption, "tipo": tipo,
                    "arquivo": arquivo, "media": arquivo, "media_file": arquivo,
                    "video_file": arquivo, "imagem": arquivo,
                    "badge": BADGE_TEXTO, "cor": COR_TEMA, "perfil": post_perfil
                })
                print(f"  [OK] Post {sc} ({tipo}) baixado de @{post_perfil}")
                if len(posts_a_manter) >= TOTAL_MIDIAS: break
        browser.close()

    if len(posts_a_manter) < 6:
        print(f"Poucas midias obtidas ({len(posts_a_manter)}). Mantendo grade atual.")
        return

    json_final = []
    for idx, post in enumerate(posts_a_manter, 1):
        ext = os.path.splitext(post["arquivo"])[1]
        nome = f"media_{idx}{ext}"
        if os.path.exists(post["arquivo"]):
            if os.path.exists(nome) and nome != post["arquivo"]:
                try: os.remove(nome)
                except Exception: pass
            try: os.rename(post["arquivo"], nome)
            except Exception: pass
        post["arquivo"] = post["media"] = post["media_file"] = post["video_file"] = post["imagem"] = nome
        json_final.append(post)

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(json_final, f, indent=2, ensure_ascii=False)
    print(f"Sucesso! {len(json_final)} midias salvas e data.json atualizado.")

if __name__ == "__main__":
    main()