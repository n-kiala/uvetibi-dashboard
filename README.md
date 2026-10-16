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

## Journees locales (verifiees, non publiees)

Pour consulter des journees dans la version locale sans les publier : copier
le dossier de chaque journee (`JJ-MM-AAAA`, avec son tableur `suivi_dechet_*.xlsx`
et un sous-dossier d'images par plaque) dans `lots_locaux/`. Le dashboard local
les ajoute aux constats BigQuery, sous la forme exacte que leur donnera
l'ingestion (une ligne par plaque et type), et affiche un bandeau « Version
locale ». Rien n'est ecrit dans BigQuery ni dans Cloud Storage ; `lots_locaux/`
est exclu du depot, la version en ligne ne voit donc jamais ces journees. Une
journee deja presente dans BigQuery n'est jamais comptee deux fois.

Pour publier une journee locale (elle devient alors visible en ligne) :

    python ingerer_suivi.py lots_locaux/07-09-2026 lots_locaux/07-09-2026/suivi_déchet_07_09_2026.xlsx --feuille 2026_09_07
    python ingerer_suivi.py ... --execute

Un autre dossier peut etre designe par la variable d'environnement `TIBI_LOTS_LOCAUX`.

## Regles d'affichage cote client

- **Photo de plaque** : chaque dossier de camion contient la photo de sa plaque
  d'immatriculation, nommee `plaque_...` (ou `Plaque_immat_...` dans la galerie
  publiee). Elle est toujours la premiere image de la galerie. Un camion sans
  photo de plaque (plaque illisible dans toutes ses videos) n'est pas affiche,
  comme un constat sans immatriculation (« X »). Les photos manquantes se
  completent avec `cvat-export\photos_plaques.py` (puis floutage des visages).
- **Decisions sur les incoherences** : `corrections_plaques.json` (ecrit par
  la fenetre `cvat-export\decisions_plaques.py`) est applique a l'affichage,
  sans toucher aux tableurs, aux dossiers ni a BigQuery :
  - `corrections` : plaque mal saisie remplacee par la bonne (et heure, pour
    les constats publies a une heure fictive) ;
  - `decisions_donnees` : lignes du tableur ignorees (saisie en double, par
    numero de ligne) et images retirees d'une galerie (image rangee aussi
    chez un autre camion, ou version en double d'une meme image).
  Ce fichier est exclu du depot (`*.json`) : pour que la version en ligne en
  tienne compte, corriger a la source (tableur avant ingestion, ou BigQuery)
  ou versionner ce fichier explicitement. `ingerer_suivi.py` ne l'applique pas.
- **Indicateurs** : le graphique, les boutons de jour et la rangee du jour
  portent toujours sur tous les vehicules, quel que soit le vehicule choisi.
  On choisit un vehicule uniquement dans la liste « Vehicules concernes ce
  jour » (plus de menu deroulant en doublon) ; ses propres indicateurs (jour et
  periode) s'affichent alors dans un bloc a son nom, au-dessus de sa galerie.
- **Types** : Textile est masque ; Incertain est affiche. La definition de
  chaque categorie (`DEFINITIONS_TYPES` dans `config.py`) est rappelee sous le
  graphique.

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
