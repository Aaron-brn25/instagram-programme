"""
meta_api — appels de base à l'API Graph de Meta (bibliothèque standard seulement).

Utilisé par meta_commun.py (sur le PC) et recopié tel quel dans le dépôt public GitHub
qui publie les Reels Instagram à l'heure (moteur_commun/github_ig/, voir son LISEZMOI.md).
`c` = {"page_id", "jeton_page", "ig_id"} d'une chaîne (Stats/config/meta_<chaine>.json).
"""
import datetime
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid

VERSION = "v23.0"   # même version que Stats/collecteurs/meta.py
GRAPH = f"https://graph.facebook.com/{VERSION}"
RUPLOAD = "https://rupload.facebook.com"


class ConteneurPerdu(RuntimeError):
    """Meta a rejeté ou laissé expirer la vidéo envoyée : il faut la renvoyer."""


def api(methode, chemin, fichier=None, **params):
    """Graph API. `fichier` : envoyé en multipart dans le champ « source ». Le jeton n'apparaît jamais dans l'erreur."""
    url = chemin if chemin.startswith("http") else f"{GRAPH}/{chemin}"
    if methode == "GET":
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params))
    elif fichier:
        b = uuid.uuid4().hex
        corps = b"".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                         for k, v in params.items())
        with open(fichier, "rb") as f:
            corps += (f'--{b}\r\nContent-Disposition: form-data; name="source"; filename="{os.path.basename(fichier)}"\r\n'
                      f"Content-Type: application/octet-stream\r\n\r\n").encode() + f.read() + f"\r\n--{b}--\r\n".encode()
        req = urllib.request.Request(url, data=corps, headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(), method=methode)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            err = json.load(e).get("error", {})
        except ValueError:
            err = {}
        raise RuntimeError(f"{chemin.split('?')[0]} : HTTP {e.code} {err.get('message', e.reason)}") from None


def televerser(url, jeton, mp4):
    with open(mp4, "rb") as f:
        donnees = f.read()
    req = urllib.request.Request(url, data=donnees, method="POST", headers={
        "Authorization": f"OAuth {jeton}", "offset": "0", "file_size": str(len(donnees)),
        "Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            rep = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"téléversement : HTTP {e.code} {e.read()[:300]!r}") from None
    if not rep.get("success", True):
        raise RuntimeError(f"téléversement refusé : {rep}")


def url_couverture(c, png):
    """Instagram ne prend la couverture que par URL publique : la miniature est déposée en photo non publiée de la Page.
    shortcut: ces photos restent cachées dans la Page, à supprimer si elles gênent un jour."""
    pid = api("POST", f"{c['page_id']}/photos", fichier=png, published="false", access_token=c["jeton_page"])["id"]
    return api("GET", pid, fields="images", access_token=c["jeton_page"])["images"][0]["source"]


def preparer_instagram(c, legende, mp4, png, journal=print):
    """Crée le conteneur du Reel et envoie la vidéo ; Meta la traite ensuite (quelques minutes). Rend l'id du conteneur."""
    params = dict(media_type="REELS", upload_type="resumable", share_to_feed="true",
                  caption=legende, access_token=c["jeton_page"])
    try:
        params["cover_url"] = url_couverture(c, png)
    except Exception as e:  # noqa: BLE001
        journal(f"instagram : miniature non appliquée, 1re image à la place ({e})")
    cont = api("POST", f"{c['ig_id']}/media", **params)["id"]
    televerser(f"{RUPLOAD}/ig-api-upload/{VERSION}/{cont}", c["jeton_page"], mp4)
    return cont


def publier_instagram(c, cont):
    """Lien du Reel publié, ou None si Meta traite encore la vidéo."""
    etat = api("GET", cont, fields="status_code,status", access_token=c["jeton_page"])
    if etat.get("status_code") in ("ERROR", "EXPIRED"):
        raise ConteneurPerdu(f"conteneur {etat}")
    if etat.get("status_code") != "FINISHED":
        return None
    media = api("POST", f"{c['ig_id']}/media_publish", creation_id=cont, access_token=c["jeton_page"])["id"]
    try:  # le Reel est en ligne : un échec ici ne doit pas le faire republier
        return api("GET", media, fields="permalink", access_token=c["jeton_page"]).get("permalink") or media
    except Exception:  # noqa: BLE001
        return media


def deja_publie(c, legende, heures=6):
    """Lien d'un Reel récent qui a déjà cette légende (garde-fou contre une double publication), sinon None."""
    depuis = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=heures)
    for m in api("GET", f"{c['ig_id']}/media", fields="caption,timestamp,permalink", limit=15,
                 access_token=c["jeton_page"]).get("data", []):
        quand = datetime.datetime.strptime(m["timestamp"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
        if quand >= depuis and (m.get("caption") or "").strip() == legende.strip():
            return m.get("permalink") or m["id"]
    return None
