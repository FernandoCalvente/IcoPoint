from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
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
    password = db.Column(db.String(200))
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
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            if user.admin:
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('dashboard'))
        else:
            error = "Usuario o contraseña incorrectos"
    return render_template('login.html', error=error)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ---------- REGISTRO ----------
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            return "Usuario ya existe"
        hashed_pw = generate_password_hash(password)
        user = User(username=username, password=hashed_pw, admin=False)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

# ---------- DASHBOARD USUARIO ----------
@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    if current_user.admin:
        return redirect(url_for('admin_dashboard'))

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

    # Periodo del 21 al 20
    hoy = date.today()
    if hoy.day >= 21:
        inicio_periodo = date(hoy.year, hoy.month, 21)
        fin_periodo = date(hoy.year + (hoy.month == 12), (hoy.month % 12) + 1, 20)
    else:
        mes_anterior = hoy.month - 1 if hoy.month > 1 else 12
        año = hoy.year if hoy.month > 1 else hoy.year - 1
        inicio_periodo = date(año, mes_anterior, 21)
        fin_periodo = date(hoy.year, hoy.month, 20)

    ordenes = Orden.query.filter(Orden.user_id==current_user.id,
                                 Orden.fecha>=inicio_periodo, Orden.fecha<=fin_periodo).all()
    total_puntos = sum(o.puntos for o in ordenes)
    objetivo = 225
    progreso = round((total_puntos / objetivo) * 100, 2)

    # Top 10 ranking
    usuarios = User.query.filter_by(admin=False).all()
    ranking_list = []
    for u in usuarios:
        total = sum(o.puntos for o in Orden.query.filter_by(user_id=u.id).all())
        ranking_list.append((u.username, total))
    ranking_list.sort(key=lambda x: x[1], reverse=True)
    top10 = ranking_list[:10]

    return render_template('dashboard.html', ordenes=ordenes, total_puntos=total_puntos, progreso=progreso, ranking=top10)

# ---------- ADMIN PANEL ----------
@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.admin:
        return "No autorizado"
    usuarios = User.query.all()
    ordenes = Orden.query.all()
    # Ranking completo sin admin
    ranking = []
    for u in usuarios:
        if u.admin:
            continue
        total = sum(o.puntos for o in Orden.query.filter_by(user_id=u.id).all())
        ranking.append((u.username, total))
    ranking.sort(key=lambda x: x[1], reverse=True)
    return render_template('admin_dashboard.html', usuarios=usuarios, ordenes=ordenes, ranking=ranking)

# ---------- CREAR / MODIFICAR / ELIMINAR USUARIOS ----------
@app.route('/usuarios/crear', methods=['GET','POST'])
@login_required
def crear_usuario():
    if not current_user.admin:
        return "No autorizado"
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        es_admin = request.form.get('admin') == 'on'
        if User.query.filter_by(username=username).first():
            return "Usuario ya existe"
        hashed_pw = generate_password_hash(password)
        user = User(username=username, password=hashed_pw, admin=es_admin)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('admin_dashboard'))
    return render_template('crear_usuario.html')

@app.route('/usuarios/modificar/<int:user_id>', methods=['GET','POST'])
@login_required
def modificar_usuario(user_id):
    if not current_user.admin:
        return "No autorizado"
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        user.username = request.form['username']
        password = request.form.get('password')
        if password:
            user.password = generate_password_hash(password)
        user.admin = request.form.get('admin') == 'on'
        db.session.commit()
        return redirect(url_for('admin_dashboard'))
    return render_template('modificar_usuario.html', user=user)

@app.route('/usuarios/eliminar/<int:user_id>')
@login_required
def eliminar_usuario(user_id):
    if not current_user.admin:
        return "No autorizado"
    user = User.query.get_or_404(user_id)
    if user.username != "admin":
        db.session.delete(user)
        db.session.commit()
    return redirect(url_for('admin_dashboard'))

# ---------- MODIFICAR Y ELIMINAR ORDENES ----------
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

# ---------- RANKING ----------
@app.route("/ranking")
@login_required
def ranking():
    mostrar_todo = request.args.get('todo', '0')  # si viene ?todo=1, mostramos todo
    usuarios = User.query.filter(User.admin==False).all()  # excluimos admin
    ranking_list = []

    for u in usuarios:
        total = sum(o.puntos for o in Orden.query.filter_by(user_id=u.id).all())
        ranking_list.append((u.username, total))

    # Ordenamos de mayor a menor
    ranking_list.sort(key=lambda x: x[1], reverse=True)

    # Para usuarios normales o si no se ha hecho click en "Ver todo", limitamos a top 10
    if not current_user.admin or mostrar_todo == '0':
        ranking_list = ranking_list[:10]

    return render_template("ranking.html", ranking=ranking_list, mostrar_todo=mostrar_todo)



# ---------- HISTORIAL ---------
@login_required
@app.route("/historial")
def historial():
    # Parámetros GET para navegar por periodos
    mes = request.args.get('mes', type=int)
    año = request.args.get('anio', type=int)

    hoy = date.today()
    if not mes or not año:
        # Si no vienen, usamos periodo actual
        if hoy.day > 20:
            mes = hoy.month
            año = hoy.year
        else:
            mes = hoy.month - 1 if hoy.month > 1 else 12
            año = hoy.year if hoy.month > 1 else hoy.year - 1

    inicio = date(año, mes, 21)
    if mes == 12:
        fin = date(año + 1, 1, 20)
    else:
        fin = date(año, mes + 1, 20)

    if current_user.admin:
        ordenes = Orden.query.filter(
            Orden.fecha >= inicio,
            Orden.fecha <= fin
        ).order_by(Orden.fecha.desc()).all()
    else:
        ordenes = Orden.query.filter(
            Orden.user_id == current_user.id,
            Orden.fecha >= inicio,
            Orden.fecha <= fin
        ).order_by(Orden.fecha.desc()).all()

    # Mes anterior y siguiente para navegación
    mes_anterior = mes - 1 if mes > 1 else 12
    año_anterior = año if mes > 1 else año - 1
    mes_siguiente = mes + 1 if mes < 12 else 1
    año_siguiente = año if mes < 12 else año + 1

    return render_template(
        "historial.html",
        ordenes=ordenes,
        inicio=inicio,
        fin=fin,
        mes_anterior=mes_anterior,
        año_anterior=año_anterior,
        mes_siguiente=mes_siguiente,
        año_siguiente=año_siguiente
    )

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
        # Crear admin si no existe
        if not User.query.filter_by(username="admin").first():
            admin_user = User(username="admin", password=generate_password_hash("AdminIcopoint2026!"), admin=True)
            db.session.add(admin_user)
            db.session.commit()
            print("Usuario administrador creado con contraseña: AdminIcopoint2026!")
    app.run(debug=True, host="0.0.0.0", port=5000)
