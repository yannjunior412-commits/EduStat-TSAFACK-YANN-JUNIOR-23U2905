from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import pandas as pd
import io, os

app = Flask(__name__)
CORS(app)

# ── Base de données Supabase (PostgreSQL) ──────────────────────────
# Sur Railway, la variable DATABASE_URL est injectée automatiquement
# Sur Supabase, on utilise l'URL de connexion PostgreSQL
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///edustat_local.db')

# Supabase renvoie parfois "postgres://" au lieu de "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

db = SQLAlchemy(app)

with app.app_context():
    try:
        db.create_all()
        print("Connexion réussie.")
    except Exception as e:
        print(f"Erreur de connexion (ignorée pour le build) : {e}")
# ── Identité de l'étudiant ─────────────────────────────────────────
ETUDIANT = {
    "nom"       : "TSAFACK",
    "prenom"    : "YANN JUNIOR",
    "matricule" : "23U2905",
    "filiere"   : "INFO-FONDA",
    "niveau"    : "Licence 2 (L2)",
    "annee"     : "2025/2026"
}

# ── Modèle de données ──────────────────────────────────────────────
class Enquete(db.Model):
    __tablename__ = 'enquetes'

    id            = db.Column(db.Integer, primary_key=True)
    # Identité
    nom           = db.Column(db.String(100), nullable=False)
    prenom        = db.Column(db.String(100), nullable=False)
    sexe          = db.Column(db.String(10),  nullable=False)
    region        = db.Column(db.String(50),  nullable=False)
    # Académique
    universite    = db.Column(db.String(150), nullable=False)
    faculte       = db.Column(db.String(150), nullable=False)
    filiere       = db.Column(db.String(100), nullable=False)
    niveau_univ   = db.Column(db.String(40),  nullable=False)
    # Résultat
    matiere       = db.Column(db.String(80),  nullable=False)
    note          = db.Column(db.Float,       nullable=False)
    # Métadonnée
    date_collecte = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ── Routes ─────────────────────────────────────────────────────────

@app.route('/')
def index():
    total   = Enquete.query.count()
    recents = Enquete.query.order_by(Enquete.date_collecte.desc()).limit(5).all()
    return render_template('index.html', total=total, recents=recents, etudiant=ETUDIANT)

@app.route('/formulaire', methods=['GET', 'POST'])
def formulaire():
    if request.method == 'POST':
        try:
            e = Enquete(
                nom         = request.form['nom'].strip().upper(),
                prenom      = request.form['prenom'].strip().title(),
                sexe        = request.form['sexe'],
                region      = request.form['region'],
                universite  = request.form['universite'],
                faculte     = request.form['faculte'],
                filiere     = request.form['filiere'],
                niveau_univ = request.form['niveau_univ'],
                matiere     = request.form['matiere'],
                note        = float(request.form['note']),
            )
            db.session.add(e)
            db.session.commit()
            return redirect(url_for('formulaire', success=1))
        except Exception as ex:
            db.session.rollback()
            return render_template('formulaire.html', etudiant=ETUDIANT, erreur=str(ex))
    return render_template('formulaire.html', etudiant=ETUDIANT)

@app.route('/dashboard')
def dashboard():
    data = Enquete.query.all()
    if not data:
        return render_template('dashboard.html', stats={}, vide=True, etudiant=ETUDIANT)

    df = pd.DataFrame([{
        'note'       : d.note,
        'matiere'    : d.matiere,
        'region'     : d.region,
        'niveau_univ': d.niveau_univ,
        'filiere'    : d.filiere,
        'faculte'    : d.faculte,
        'sexe'       : d.sexe,
        'universite' : d.universite,
    } for d in data])

    def top(serie, n=5):
        return serie.nlargest(n).round(2).to_dict()

    stats = {
        'total'        : len(df),
        'moyenne'      : round(df['note'].mean(), 2),
        'mediane'      : round(df['note'].median(), 2),
        'ecart_type'   : round(df['note'].std(), 2),
        'min'          : round(df['note'].min(), 2),
        'max'          : round(df['note'].max(), 2),
        'admis'        : int((df['note'] >= 10).sum()),
        'echec'        : int((df['note'] < 10).sum()),
        'par_matiere'  : df.groupby('matiere')['note'].mean().round(2).to_dict(),
        'par_niveau'   : df.groupby('niveau_univ')['note'].mean().round(2).to_dict(),
        'par_filiere'  : df.groupby('filiere')['note'].mean().round(2).to_dict(),
        'par_faculte'  : df.groupby('faculte')['note'].mean().round(2).to_dict(),
        'par_sexe'     : df.groupby('sexe')['note'].mean().round(2).to_dict(),
        'par_region'   : df.groupby('region')['note'].mean().round(2).to_dict(),
        'par_univ'     : df.groupby('universite')['note'].mean().round(2).to_dict(),
    }
    return render_template('dashboard.html', stats=stats, vide=False, etudiant=ETUDIANT)

@app.route('/donnees')
def donnees():
    page = request.args.get('page', 1, type=int)
    data = Enquete.query.order_by(
        Enquete.date_collecte.desc()
    ).paginate(page=page, per_page=20, error_out=False)
    return render_template('donnees.html', data=data, etudiant=ETUDIANT)

@app.route('/export/csv')
def export_csv():
    data = Enquete.query.all()
    df = pd.DataFrame([{
        'ID'          : d.id,
        'Nom'         : d.nom,
        'Prenom'      : d.prenom,
        'Sexe'        : d.sexe,
        'Region'      : d.region,
        'Universite'  : d.universite,
        'Faculte'     : d.faculte,
        'Filiere'     : d.filiere,
        'Niveau'      : d.niveau_univ,
        'Matiere'     : d.matiere,
        'Note'        : d.note,
        'Date'        : d.date_collecte.strftime('%d/%m/%Y %H:%M'),
    } for d in data])
    buf = io.BytesIO()
    df.to_csv(buf, index=False, encoding='utf-8-sig')
    buf.seek(0)
    return send_file(buf, mimetype='text/csv', as_attachment=True,
                     download_name='edustat_TSAFACK_23U2905.csv')

@app.route('/export/excel')
def export_excel():
    data = Enquete.query.all()
    df = pd.DataFrame([{
        'ID'          : d.id,
        'Nom'         : d.nom,
        'Prenom'      : d.prenom,
        'Sexe'        : d.sexe,
        'Region'      : d.region,
        'Universite'  : d.universite,
        'Faculte'     : d.faculte,
        'Filiere'     : d.filiere,
        'Niveau'      : d.niveau_univ,
        'Matiere'     : d.matiere,
        'Note'        : d.note,
        'Date'        : d.date_collecte.strftime('%d/%m/%Y %H:%M'),
    } for d in data])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='EduStat_TSAFACK')
    buf.seek(0)
    return send_file(buf,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='edustat_TSAFACK_23U2905.xlsx')

@app.route('/health')
def health():
    return jsonify({"status": "ok", "etudiant": ETUDIANT['matricule']})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
