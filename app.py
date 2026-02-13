from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
from werkzeug.security import generate_password_hash, check_password_hash




import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mi_clave_secreta_icopoint'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///icopoint.db'
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ---------- MODELOS ----------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(50))
    admin = db.Column(db.Boolean, default=False)

class Orden(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    numero_instalacion = db.Column(db.String(50))
    fecha = db.Column(db.Date)
    tipo = db.Column(db.String(50))
    subtipos = db.Column(db.String(200))
    puntos = db.Column(db.Float)

# ---------- LOGIN ----------
@app.route('/', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            error = "Usuario o contraseña incorrectos"

    return render_template('login.html', error=error)

# ---------- RUTAS ----------
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            login_user(user)
            return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            return "Usuario ya existe"
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

# ---------- DASHBOARD ----------
@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    if request.method == 'POST':
        numero = request.form['numero_instalacion']
        fecha = datetime.strptime(request.form['fecha'], '%Y-%m-%d').date()
        tipo = request.form['tipo']
        subtipos = request.form.getlist('subtipo')
        puntos = calcular_puntos(tipo, subtipos)
        orden = Orden(user_id=current_user.id, numero_instalacion=numero, fecha=fecha,
                      tipo=tipo, subtipos=', '.join(subtipos), puntos=puntos)
        db.session.add(orden)
        db.session.commit()

    hoy = datetime.now().date()
    if hoy.day >= 21:
        inicio_periodo = datetime(hoy.year, hoy.month, 21).date()
        fin_periodo = datetime(hoy.year + (hoy.month == 12), (hoy.month % 12) + 1, 20).date()
    else:
        mes_anterior = hoy.month - 1 if hoy.month > 1 else 12
        año = hoy.year if hoy.month > 1 else hoy.year - 1
        inicio_periodo = datetime(año, mes_anterior, 21).date()
        fin_periodo = datetime(hoy.year, hoy.month, 20).date()

    if current_user.admin:
        ordenes = Orden.query.filter(Orden.fecha>=inicio_periodo, Orden.fecha<=fin_periodo).all()
    else:
        ordenes = Orden.query.filter(Orden.user_id==current_user.id, Orden.fecha>=inicio_periodo, Orden.fecha<=fin_periodo).all()

    total_puntos = sum(o.puntos for o in ordenes if o.user_id==current_user.id)
    objetivo = 225
    progreso = round((total_puntos / objetivo) * 100, 2)

    return render_template('dashboard.html', ordenes=ordenes, total_puntos=total_puntos, progreso=progreso)

# ---------- MODIFICAR Y ELIMINAR ----------
@app.route('/eliminar/<int:orden_id>')
@login_required
def eliminar(orden_id):
    orden = Orden.query.get_or_404(orden_id)
    if orden.user_id == current_user.id or current_user.admin:
        db.session.delete(orden)
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/modificar/<int:orden_id>', methods=['GET','POST'])
@login_required
def modificar(orden_id):
    orden = Orden.query.get_or_404(orden_id)
    if orden.user_id != current_user.id and not current_user.admin:
        return "No autorizado"

    if request.method == 'POST':
        orden.numero_instalacion = request.form['numero_instalacion']
        orden.fecha = datetime.strptime(request.form['fecha'], '%Y-%m-%d').date()
        orden.tipo = request.form['tipo']
        orden.subtipos = ', '.join(request.form.getlist('subtipo'))
        orden.puntos = calcular_puntos(orden.tipo, request.form.getlist('subtipo'))
        db.session.commit()
        return redirect(url_for('dashboard'))

    subtipos_dict = {
        "Instalación Residencial": ["Interior -80m","Interior +80m","Exterior -80m","Exterior +80m","Poste -80m","Poste +80m","Poste +220m","TV","Reutilizada Interior/Exterior","Reutilizada Poste"],
        "Instalación B2B": ["Acceso+Router Nueva","Acceso+Router Reutilizada","Acceso GGCC Nueva","Acceso GGCC Reutilizada","Acceso+Router Centrex Nueva","Acceso+Router Centrex Reutilizada","Poste Nueva","Poste Reutilizada","Postventa","Portabilidad Express","Replanteo","Instalación TV","Avería"],
        "Avería": ["Interior/Exterior","Poste","Fin de semana","Fin de semana Poste"],
        "Postventa": ["Postventa"]
    }

    return render_template('modificar.html', orden=orden, subtipos=subtipos_dict)

# ---------- HISTORIAL ----------
from datetime import datetime, date, timedelta


@login_required
@app.route("/historial")
def historial():
    hoy = date.today()

    # Si hoy es después del día 20, el periodo es del 21 de este mes al 20 del siguiente
    if hoy.day > 20:
        inicio = date(hoy.year, hoy.month, 21)
        # Manejar diciembre -> enero
        if hoy.month == 12:
            fin = date(hoy.year + 1, 1, 20)
        else:
            fin = date(hoy.year, hoy.month + 1, 20)
    else:
        # Hoy es antes del 21: periodo del 21 del mes anterior al 20 de este mes
        if hoy.month == 1:
            inicio = date(hoy.year - 1, 12, 21)
        else:
            inicio = date(hoy.year, hoy.month - 1, 21)
        fin = date(hoy.year, hoy.month, 20)

    ordenes = Orden.query.filter(
        Orden.user_id == current_user.id,
        Orden.fecha >= inicio,
        Orden.fecha <= fin
    ).all()

    return render_template("historial.html", ordenes=ordenes)


# ---------- RANKING ----------

@app.route("/ranking")
def ranking():
    usuarios = User.query.all()
    ranking_list = []
    for u in usuarios:
        total = sum(o.puntos for o in Orden.query.filter_by(user_id=u.id).all())
        ranking_list.append((u.username, total))

    # Ordenamos de mayor a menor
    ranking_list.sort(key=lambda x: x[1], reverse=True)

    # Solo los 10 primeros
    ranking_top10 = ranking_list[:10]

    return render_template("ranking.html", ranking=ranking_top10)


# ---------- CALCULO DE PUNTOS ----------
def calcular_puntos(tipo, subtipos):
    puntos = 0
    for st in subtipos:
        if tipo == "Avería":
            if st == "Interior/Exterior": puntos += 1.95
            elif st == "Poste": puntos += 1.95 + 1.99
            elif st == "Fin de semana": puntos += 2.04
            elif st == "Fin de semana Poste": puntos += 2.04 + 2.99
        elif tipo == "Postventa":
            puntos += 1.77
        elif tipo == "Instalación Residencial":
            mapping = {
                "Interior -80m":3.80,"Interior +80m":4.56,"Exterior -80m":4.23,"Exterior +80m":5.09,
                "Poste -80m":8.01,"Poste +80m":8.83,"Poste +220m":9.18,"TV":0.43,
                "Reutilizada Interior/Exterior":2.60,"Reutilizada Poste":4.37
            }
            puntos += mapping.get(st,0)
        elif tipo == "Instalación B2B":
            mapping = {
                "Acceso+Router Nueva":6.23,"Acceso+Router Reutilizada":4.90,
                "Acceso GGCC Nueva":4.68,"Acceso GGCC Reutilizada":3.35,
                "Acceso+Router Centrex Nueva":7.15,"Acceso+Router Centrex Reutilizada":5.82,
                "Poste Nueva":2.70,"Poste Reutilizada":1.38,
                "Postventa":2.02,"Portabilidad Express":2.14,"Replanteo":3.16,
                "Instalación TV":0.46,"Avería":2.14
            }
            puntos += mapping.get(st,0)
    return puntos

# ---------- INICIALIZAR DB ----------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        # Crear usuario administrador si no existe
        if not User.query.filter_by(username="admin").first():
            admin_user = User(
                username="admin",
                password=generate_password_hash("AdminIcopoint2026!"),
                admin=True
            )
            db.session.add(admin_user)
            db.session.commit()
            print("Usuario administrador creado")

    # Solo para entorno LOCAL
    app.run(debug=True)

