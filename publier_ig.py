"""
publier_ig — publie à l'heure les Reels Instagram en file d'attente. Tourne sur GitHub Actions (instagram.yml), PC éteint.

file/<chaine>__<id>.json : {"chaine", "id", "quand" (ISO, UTC), "legende", "video", "miniature"}
  vidéo et miniature : fichiers de la release « file » du dépôt, déposés à l'avance par meta.py envoyer.
Chaque passage (toutes les 10 min) prend les Reels dont l'heure tombe dans les 25 min, envoie la vidéo chez Meta,
attend l'heure exacte, puis publie. Réussi : la fiche est supprimée et une ligne ajoutée à journal.log.
Plus de 2 h de retard : la fiche part dans echecs/ et le passage échoue (GitHub prévient par e-mail).
Secret META_JETONS : {"<chaine>": {"page_id", "jeton_page", "ig_id"}}.
"""
import datetime
import glob
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

import meta_api as m

AVANT = datetime.timedelta(minutes=25)
RETARD_MAX = datetime.timedelta(hours=2)
TAG = "file"
REPO = os.environ.get("GITHUB_REPOSITORY", "")
echecs = 0


def maintenant():
    return datetime.datetime.now(datetime.timezone.utc)


def journal(msg):
    ligne = f"{maintenant():%Y-%m-%d %H:%M} UTC {msg}"
    print(ligne, flush=True)
    with open("journal.log", "a", encoding="utf-8") as f:
        f.write(ligne + "\n")


def retirer_fichiers(e):
    for nom in (e["video"], e["miniature"]):
        subprocess.run(["gh", "release", "delete-asset", TAG, nom, "--yes", "--repo", REPO], check=False)


def fini(chemin, e, url):
    os.remove(chemin)
    retirer_fichiers(e)
    journal(f"PUBLIÉ {e['chaine']} {e['id']} {url}")


def echec(chemin, e, raison):
    global echecs
    echecs += 1
    os.makedirs("echecs", exist_ok=True)
    e["erreur"] = raison
    with open(os.path.join("echecs", os.path.basename(chemin)), "w", encoding="utf-8") as f:
        json.dump(e, f, ensure_ascii=False, indent=1)
    os.remove(chemin)
    journal(f"ÉCHEC  {e['chaine']} {e['id']} : {raison}")


def telecharger(nom, dossier):
    dest = os.path.join(dossier, nom)
    urllib.request.urlretrieve(f"https://github.com/{REPO}/releases/download/{TAG}/{nom}", dest)
    return dest


def main():
    jetons = json.loads(os.environ["META_JETONS"])
    prets = []
    for chemin in sorted(glob.glob("file/*.json")):
        with open(chemin, encoding="utf-8") as f:
            e = json.load(f)
        t = datetime.datetime.fromisoformat(e["quand"])
        if maintenant() > t + RETARD_MAX:
            echec(chemin, e, "jamais publié dans les 2 h (erreurs répétées ?)")
        elif t - AVANT <= maintenant():
            prets.append((t, chemin, e))
    envoyes = []
    for t, chemin, e in sorted(prets, key=lambda x: x[0]):
        c = jetons[e["chaine"]]
        try:
            url = m.deja_publie(c, e["legende"], heures=3)
            if url:
                fini(chemin, e, url)
                continue
            dossier = tempfile.mkdtemp()
            cont = m.preparer_instagram(c, e["legende"], telecharger(e["video"], dossier),
                                        telecharger(e["miniature"], dossier), journal)
            envoyes.append((t, chemin, e, c, cont))
        except Exception as ex:  # noqa: BLE001  (on retente au passage suivant)
            journal(f"ERREUR {e['chaine']} {e['id']} (envoi) : {ex}")
    for t, chemin, e, c, cont in envoyes:
        attente = (t - maintenant()).total_seconds()
        if attente > 0:
            time.sleep(attente)
        try:
            for _ in range(40):   # Meta traite la vidéo : 20 min au plus
                url = m.publier_instagram(c, cont)
                if url:
                    fini(chemin, e, url)
                    break
                time.sleep(30)
            else:
                journal(f"ERREUR {e['chaine']} {e['id']} : vidéo toujours en traitement chez Meta")
        except Exception as ex:  # noqa: BLE001
            journal(f"ERREUR {e['chaine']} {e['id']} (publication) : {ex}")
    sys.exit(1 if echecs else 0)


if __name__ == "__main__":
    main()
