from flask_migrate import Migrate
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import pandas as pd

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///usuarios.db'
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'static', 'uploads')
db = SQLAlchemy(app)
migrate = Migrate(app, db)
bcrypt = Bcrypt(app)

# Verificar si la carpeta de uploads existe, si no, crearla
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Tipos de archivo permitidos para la subida
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Modelo de Usuarios


class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo_electronico = db.Column(db.String(100), unique=True, nullable=False)
    contrasena = db.Column(db.String(200), nullable=False)
    rol = db.Column(db.String(10), nullable=False)  # admin o agente
    foto_perfil = db.Column(db.String(200), nullable=True)

# Modelo de Turnos


class Turno(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    agente_id = db.Column(db.Integer, db.ForeignKey(
        'usuario.id'), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fin = db.Column(db.Time, nullable=False)

    # Campos adicionales para registrar las horas de entrada, salida, desayuno y almuerzo
    hora_entrada = db.Column(db.Time, nullable=True)
    hora_salida = db.Column(db.Time, nullable=True)
    hora_desayuno = db.Column(db.Time, nullable=True)
    hora_almuerzo = db.Column(db.Time, nullable=True)
    estado = db.Column(db.String(20), nullable=False, default='pendiente')

# Modelo de Notificaciones


class Notificacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey(
        'usuario.id'), nullable=False)
    mensaje = db.Column(db.String(255), nullable=False)
    leida = db.Column(db.Boolean, default=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

# Función para generar notificaciones


def generar_notificacion(usuario_id, mensaje):
    nueva_notificacion = Notificacion(usuario_id=usuario_id, mensaje=mensaje)
    db.session.add(nueva_notificacion)
    db.session.commit()

# Ruta de login


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        usuario = Usuario.query.filter_by(correo_electronico=email).first()

        if usuario and bcrypt.check_password_hash(usuario.contrasena, password):
            session['usuario_id'] = usuario.id
            session['rol'] = usuario.rol
            return redirect(url_for('dashboard_admin' if usuario.rol == 'admin' else 'dashboard_agente'))
        else:
            flash('Credenciales incorrectas, intente de nuevo.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')

# Ruta de logout


@app.route('/logout')
def logout():
    session.pop('usuario_id', None)
    session.pop('rol', None)
    return redirect(url_for('login'))

# Ruta del Dashboard de Administrador


@app.route('/dashboard_admin')
def dashboard_admin():
    if 'usuario_id' not in session or session['rol'] != 'admin':
        return redirect(url_for('login'))

    # Obtener el usuario actual
    usuario = Usuario.query.get(session['usuario_id'])

    # Obtener el resumen de usuarios y turnos
    usuarios_activos = Usuario.query.filter_by(rol='agente').count()
    turnos_totales = Turno.query.count()
    turnos_pendientes = Turno.query.filter_by(estado='pendiente').count()

    # Obtener la productividad de los agentes
    agentes = Usuario.query.filter_by(rol='agente').all()

    productividad = []
    for agente in agentes:
        turnos_agente = Turno.query.filter_by(agente_id=agente.id).all()
        total_horas_trabajadas = 0
        turnos_completados = 0
        pausas_registradas = 0
        ultima_entrada = None
        ultima_salida = None

        for turno in turnos_agente:
            if turno.hora_entrada and turno.hora_salida:
                entrada_datetime = datetime.combine(
                    turno.fecha, turno.hora_entrada)
                salida_datetime = datetime.combine(
                    turno.fecha, turno.hora_salida)
                horas_trabajadas = (
                    salida_datetime - entrada_datetime).total_seconds() / 3600
                total_horas_trabajadas += round(horas_trabajadas, 2)
                turnos_completados += 1
                ultima_entrada = turno.hora_entrada.strftime('%H:%M')
                ultima_salida = turno.hora_salida.strftime('%H:%M')

            if turno.hora_desayuno and turno.hora_almuerzo:
                pausas_registradas += 1

        productividad.append({
            'agente': agente.nombre,
            'total_horas': total_horas_trabajadas,
            'turnos_completados': turnos_completados,
            'pausas': pausas_registradas,
            'ultima_entrada': ultima_entrada,
            'ultima_salida': ultima_salida
        })

    return render_template('dashboard_admin.html', usuario=usuario, usuarios_activos=usuarios_activos,
                           turnos_totales=turnos_totales, turnos_pendientes=turnos_pendientes,
                           productividad=productividad)

# Exportar productividad


# Aquí va la parte de exportar productividad y ajustar las horas trabajadas
@app.route('/exportar_productividad')
def exportar_productividad():
    if 'usuario_id' not in session or session['rol'] != 'admin':
        return redirect(url_for('login'))

    agentes = Usuario.query.filter_by(rol='agente').all()

    data = []
    for agente in agentes:
        turnos_agente = Turno.query.filter_by(agente_id=agente.id).all()
        for turno in turnos_agente:
            if turno.hora_entrada and turno.hora_salida:
                horas_trabajadas = round((datetime.combine(turno.fecha, turno.hora_salida) -
                                          datetime.combine(turno.fecha, turno.hora_entrada)).total_seconds() / 3600, 2)
            else:
                horas_trabajadas = 'N/A'
            data.append({
                'Agente': agente.nombre,
                'Fecha': turno.fecha,
                'Horas Trabajadas': horas_trabajadas,
                'Desayuno': turno.hora_desayuno or 'No registrado',
                'Almuerzo': turno.hora_almuerzo or 'No registrado'
            })

    df = pd.DataFrame(data)
    filepath = os.path.join(
        app.config['UPLOAD_FOLDER'], 'productividad_agentes.xlsx')
    df.to_excel(filepath, index=False)

    return send_from_directory(app.config['UPLOAD_FOLDER'], 'productividad_agentes.xlsx', as_attachment=True)


# Ruta del Dashboard de Agente


@app.route('/dashboard_agente')
def dashboard_agente():
    if 'usuario_id' not in session or session['rol'] != 'agente':
        return redirect(url_for('login'))

    # Obtener el usuario actual
    usuario = Usuario.query.get(session['usuario_id'])

    # Obtener todos los turnos del día actual para el agente
    turnos_hoy = Turno.query.filter_by(
        agente_id=usuario.id, fecha=datetime.today().date()).all()

    # Si no hay turnos para hoy, mostrar un mensaje
    if not turnos_hoy:
        flash('No tienes turnos asignados para hoy.', 'info')

    # Obtener estadísticas
    turnos_completados = Turno.query.filter_by(
        agente_id=usuario.id, estado='completado').count()
    turnos_pendientes = Turno.query.filter_by(
        agente_id=usuario.id, estado='pendiente').count()

    # Obtener notificaciones no leídas
    notificaciones = Notificacion.query.filter_by(
        usuario_id=usuario.id, leida=False).all()

    # Marcar las notificaciones como leídas
    for notificacion in notificaciones:
        notificacion.leida = True
    db.session.commit()

    # Enviar la plantilla actualizada con los turnos del día y las estadísticas
    return render_template('dashboard_agente.html', usuario=usuario, turnos_hoy=turnos_hoy,
                           turnos_completados=turnos_completados, turnos_pendientes=turnos_pendientes,
                           notificaciones=notificaciones)

# Ruta para marcar un turno como completado


@app.route('/marcar_turno_completado/<int:id>', methods=['POST'])
def marcar_turno_completado(id):
    if 'usuario_id' not in session or session['rol'] != 'agente':
        return redirect(url_for('login'))

    turno = Turno.query.filter_by(
        id=id, agente_id=session['usuario_id']).first_or_404()
    turno.estado = 'completado'
    db.session.commit()

    flash('Turno marcado como completado.', 'success')
    return redirect(url_for('dashboard_agente'))

# Ruta para gestionar usuarios


@app.route('/gestion_usuarios')
def gestion_usuarios():
    if 'usuario_id' not in session or session['rol'] != 'admin':
        return redirect(url_for('login'))

    usuario = Usuario.query.get(session['usuario_id'])

    if not usuario:
        flash(
            'Hubo un problema con su sesión. Por favor, inicie sesión nuevamente.', 'danger')
        return redirect(url_for('login'))

    usuarios = Usuario.query.all()
    return render_template('gestion_usuarios.html', usuarios=usuarios, usuario=usuario)

# Ruta para editar usuario


@app.route('/editar_usuario/<int:id>', methods=['GET', 'POST'])
def editar_usuario(id):
    usuario = Usuario.query.get_or_404(id)
    if request.method == 'POST':
        nuevo_nombre = request.form['nombre']
        nuevo_correo = request.form['correo']

        usuario_existente = Usuario.query.filter_by(
            correo_electronico=nuevo_correo).first()
        if usuario_existente and usuario_existente.id != id:
            flash('El correo electrónico ya está registrado para otro usuario.', 'danger')
            return redirect(url_for('editar_usuario', id=id))

        usuario.nombre = nuevo_nombre
        usuario.correo_electronico = nuevo_correo

        if 'contrasena' in request.form and request.form['contrasena']:
            usuario.contrasena = bcrypt.generate_password_hash(
                request.form['contrasena']).decode('utf-8')

        db.session.commit()
        flash('Usuario actualizado exitosamente.', 'success')
        return redirect(url_for('gestion_usuarios'))

    return render_template('editar_usuario.html', usuario=usuario)

# Ruta para eliminar un usuario


@app.route('/eliminar_usuario/<int:id>', methods=['POST'])
def eliminar_usuario(id):
    if 'usuario_id' not in session or session['rol'] != 'admin':
        return redirect(url_for('login'))

    usuario = Usuario.query.get_or_404(id)
    db.session.delete(usuario)
    db.session.commit()

    flash('Usuario eliminado exitosamente.', 'success')
    return redirect(url_for('gestion_usuarios'))

# Ruta para editar perfil


@app.route('/editar_perfil', methods=['GET', 'POST'])
def editar_perfil():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    usuario = Usuario.query.get(session['usuario_id'])

    if request.method == 'POST':
        usuario.nombre = request.form['nombre']

        if 'foto_perfil' in request.files:
            foto = request.files['foto_perfil']
            if foto and allowed_file(foto.filename):
                filename = secure_filename(foto.filename)
                ruta_foto = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                foto.save(ruta_foto)
                usuario.foto_perfil = filename
            else:
                flash(
                    'Tipo de archivo no permitido. Solo se permiten imágenes.', 'danger')
                return redirect(url_for('editar_perfil'))

        db.session.commit()
        flash('Perfil actualizado exitosamente.', 'success')
        return redirect(url_for('dashboard_agente' if usuario.rol == 'agente' else 'dashboard_admin'))

    return render_template('editar_perfil.html', usuario=usuario)

# Ruta para servir las imágenes subidas


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Ruta para crear un usuario nuevo


@app.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    if 'usuario_id' not in session or session['rol'] != 'admin':
        return redirect(url_for('login'))

    usuario = Usuario.query.get(session['usuario_id'])

    if request.method == 'POST':
        nombre = request.form['nombre']
        correo = request.form['correo']
        contrasena = request.form['contrasena']
        rol = request.form['rol']
        contrasena_cifrada = bcrypt.generate_password_hash(
            contrasena).decode('utf-8')
        nuevo_usuario = Usuario(
            nombre=nombre, correo_electronico=correo, contrasena=contrasena_cifrada, rol=rol)
        db.session.add(nuevo_usuario)
        db.session.commit()
        flash('Usuario creado exitosamente', 'success')
        return redirect(url_for('gestion_usuarios'))

    return render_template('crear_usuario.html', usuario=usuario)

# Ruta para cargar turnos desde archivo Excel


@app.route('/cargar_excel', methods=['GET', 'POST'])
def cargar_excel():
    if 'usuario_id' not in session or session['rol'] != 'admin':
        return redirect(url_for('login'))

    usuario = Usuario.query.get(session['usuario_id'])

    if request.method == 'POST':
        file = request.files['excel_file']
        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            data = pd.read_excel(filepath)
            for index, row in data.iterrows():
                fecha = pd.to_datetime(row['fecha']).date()
                hora_inicio = pd.to_datetime(row['hora_inicio']).time()
                hora_fin = pd.to_datetime(row['hora_fin']).time()

                nuevo_turno = Turno(
                    agente_id=row['agente_id'], fecha=fecha, hora_inicio=hora_inicio, hora_fin=hora_fin)
                db.session.add(nuevo_turno)

            db.session.commit()
            flash('Archivo cargado y procesado exitosamente', 'success')
            return redirect(url_for('dashboard_admin'))

    return render_template('cargar_excel.html', usuario=usuario)

# Ruta para asignar turnos manualmente


@app.route('/asignar_turno', methods=['GET', 'POST'])
def asignar_turno():
    if 'usuario_id' not in session or session['rol'] != 'admin':
        return redirect(url_for('login'))

    usuario = Usuario.query.get(session['usuario_id'])

    if request.method == 'POST':
        agente_id = request.form['agente_id']
        fecha_str = request.form['fecha']
        hora_inicio_str = request.form['hora_inicio']
        hora_fin_str = request.form['hora_fin']

        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        hora_inicio = datetime.strptime(hora_inicio_str, '%H:%M').time()
        hora_fin = datetime.strptime(hora_fin_str, '%H:%M').time()

        # Verificar si ya existe un turno para esa fecha y agente
        turno_existente = Turno.query.filter_by(
            agente_id=agente_id, fecha=fecha).first()
        if turno_existente:
            flash('El agente ya tiene un turno asignado para esa fecha.', 'danger')
            return redirect(url_for('asignar_turno'))

        # Crear un nuevo turno
        nuevo_turno = Turno(agente_id=agente_id, fecha=fecha,
                            hora_inicio=hora_inicio, hora_fin=hora_fin)
        db.session.add(nuevo_turno)
        db.session.commit()

        generar_notificacion(
            agente_id, f"Se te ha asignado un nuevo turno para el día {fecha_str}")
        flash('Turno asignado y notificación enviada.', 'success')
        return redirect(url_for('dashboard_admin'))

    agentes = Usuario.query.filter_by(rol='agente').all()
    return render_template('asignar_turno.html', agentes=agentes, usuario=usuario)

# Ruta del historial del agente


@app.route('/historial_agente')
def historial_agente():
    if 'usuario_id' not in session or session['rol'] != 'agente':
        return redirect(url_for('login'))

    usuario = Usuario.query.get(session['usuario_id'])
    registros = Turno.query.filter_by(agente_id=usuario.id).all()

    return render_template('historial_agente.html', registros=registros, usuario=usuario)

# Ruta para marcar la entrada


@app.route('/marcar_entrada/<int:turno_id>', methods=['POST'])
def marcar_entrada(turno_id):
    if 'usuario_id' not in session or session['rol'] != 'agente':
        return jsonify({"message": "No autorizado"}), 403

    turno = Turno.query.get(turno_id)
    if turno and turno.agente_id == session['usuario_id'] and not turno.hora_entrada:
        turno.hora_entrada = datetime.now().time()
        turno.estado = 'en progreso'
        db.session.commit()

        # Generar notificación para el administrador
        generar_notificacion(turno.agente_id, f'{
                             turno.fecha}: Entrada registrada.')

        return jsonify({"message": "Entrada marcada con éxito."}), 200

    return jsonify({"message": "Error al marcar la entrada."}), 400

# Ruta para marcar la salida


@app.route('/marcar_salida/<int:turno_id>', methods=['POST'])
def marcar_salida(turno_id):
    if 'usuario_id' not in session or session['rol'] != 'agente':
        return jsonify({"message": "No autorizado"}), 403

    turno = Turno.query.get(turno_id)
    if turno and turno.agente_id == session['usuario_id'] and not turno.hora_salida:
        turno.hora_salida = datetime.now().time()
        turno.estado = 'completado'
        db.session.commit()

        # Generar notificación para el administrador
        generar_notificacion(turno.agente_id, f'{
                             turno.fecha}: Salida registrada.')

        return jsonify({"message": "Salida marcada con éxito."}), 200

    return jsonify({"message": "Error al marcar la salida."}), 400

# Ruta para marcar el desayuno


@app.route('/marcar_desayuno/<int:turno_id>', methods=['POST'])
def marcar_desayuno(turno_id):
    if 'usuario_id' not in session or session['rol'] != 'agente':
        return jsonify({"message": "No autorizado"}), 403

    turno = Turno.query.get(turno_id)
    if turno and turno.agente_id == session['usuario_id'] and not turno.hora_desayuno:
        turno.hora_desayuno = datetime.now().time()
        db.session.commit()
        return jsonify({"message": "Desayuno registrado con éxito."}), 200
    return jsonify({"message": "Error al registrar desayuno."}), 400

# Ruta para marcar el almuerzo


@app.route('/marcar_almuerzo/<int:turno_id>', methods=['POST'])
def marcar_almuerzo(turno_id):
    if 'usuario_id' not in session or session['rol'] != 'agente':
        return jsonify({"message": "No autorizado"}), 403

    turno = Turno.query.get(turno_id)
    if turno and turno.agente_id == session['usuario_id'] and not turno.hora_almuerzo:
        turno.hora_almuerzo = datetime.now().time()
        db.session.commit()
        return jsonify({"message": "Almuerzo registrado con éxito."}), 200
    return jsonify({"message": "Error al registrar almuerzo."}), 400


# Crear un usuario de ejemplo


@app.route('/crear_usuario_ejemplo')
def crear_usuario_ejemplo():
    contrasena_cifrada = bcrypt.generate_password_hash(
        'admin123').decode('utf-8')
    nuevo_usuario = Usuario(nombre="Administrador", correo_electronico="admin@empresa.com",
                            contrasena=contrasena_cifrada, rol="admin")
    db.session.add(nuevo_usuario)
    db.session.commit()
    return "Usuario creado"


# Iniciar la aplicación
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
