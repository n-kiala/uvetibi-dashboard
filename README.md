# Dashboard UVE Tibi - v3

## Arborescence

    dashboard_v3/
      app_v3.py                    vue client (lecture seule)
      config.py                    constantes, clients GCP, acces aux donnees
      ingerer_suivi.py             ingestion d'un lot Suivi_dechet (images + constats)
      pages/1_Administration.py    consultation complete + suppression (mot de passe)
      assets/                      logos NeuroGreen et Tibi
      .streamlit/secrets.toml      mot de passe admin (a creer)
      tibi-credentials.json        service account (a copier ici)

## Installation

    conda activate opencv_env
    python -m pip install -r requirements.txt

`pyarrow` et `db-dtypes` sont indispensables : sans eux, `.to_dataframe()`
leve une exception et le dashboard se retrouve sans donnees.

## Configuration

1. Copier `tibi-credentials.json` a la racine du dossier.
2. Renommer `.streamlit/secrets.toml.exemple` en `.streamlit/secrets.toml`
   et y definir le mot de passe administrateur.

## Lancement

    python -m streamlit run app_v3.py

Utiliser `python -m streamlit` et non `streamlit` seul : la commande nue peut
se resoudre vers un autre interpreteur Python que celui de l'environnement actif.

## Ajouter un lot de constats

Un lot = le dossier issu du tri manuel (un sous-dossier par plaque + le tableur
de suivi). L'ingestion ecrit aux deux endroits que lit le dashboard : les
images dans Cloud Storage et une ligne BigQuery par couple (plaque, type),
avec les counts sommes et `score_confiance = 100`.

    python ingerer_suivi.py <dossier_lot> <tableur> --feuille 2026_09_03

Sans `--execute`, rien n'est ecrit : le script affiche les lignes qu'il
inserait, les images qu'il enverrait, et signale les incoherences entre le
tableur et les dossiers (plaque sans images, image citee mais absente).
Relancer avec `--execute` pour appliquer ; un garde-fou refuse le lot si des
constats existent deja pour ce jour, pour eviter les doublons.

`--avec-photo-plaque` inclut les gros plans `Plaque_immat_*.jpg` dans la
galerie ; par defaut ils sont ecartes.

La lecture directe du `.xlsx` demande `openpyxl` (`pip install openpyxl`).
Sans lui, exporter la feuille en `.csv` et passer ce fichier au script : les
colonnes sont lues par position (Date, Heure, Plaque, Dechet, Count, Nom_img).

Un vehicule n'apparait dans la vue client que s'il lui reste au moins une
image : les constats sans image sont masques.

## Mise en ligne (Streamlit Community Cloud)

Les identifiants ne sont jamais versionnes : `config.py` lit d'abord le secret
`gcp_service_account`, et ne retombe sur `tibi-credentials.json` qu'en local.
`.gitignore` exclut la cle, les secrets et les poids de modeles.

1. Creer le depot, en verifiant d'abord ce qui serait pousse :

        git init
        git add .
        git status              # tibi-credentials.json ne doit PAS apparaitre
        git commit -m "Dashboard UVE Tibi"

2. Pousser sur un depot GitHub **prive**.
3. Sur share.streamlit.io : New app, choisir le depot, fichier principal
   `app_v3.py`.
4. Settings > Secrets : coller le contenu de `.streamlit/secrets.toml`
   (rubrique `gcp_service_account` + `admin_password`).

Points a surveiller :

- `AUTORISER_SUPPRESSION` doit rester a `False` : sinon la vue client expose un
  bouton qui supprime images et constats.
- La page Administration n'est servie que si elle est placee dans `pages/`.
  Tant qu'elle reste a la racine, elle est inaccessible en ligne - ce qui est
  souhaitable pour un deploiement ouvert.
- Le tableau de bord affiche des plaques et des photos de vehicules :
  restreindre l'acces (app privee, liste d'e-mails) des que le lien sort du
  cercle projet.

## Notes

- Le bucket ne contient pas de miniatures. Les vignettes sont generees a la
  volee et mises en cache 30 minutes ; le premier affichage d'une journee est
  donc plus lent que les suivants.
- La page Administration apparait dans la navigation laterale mais reste
  inaccessible sans mot de passe. Pour la masquer completement, deplacer le
  fichier hors de `pages/` et le lancer comme une application distincte.
