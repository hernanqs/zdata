from flask import Flask, render_template, request, g, jsonify, redirect, url_for
import pandas as pd
import sqlite3
import re
import os
from flask_wtf import FlaskForm
from wtforms import FieldList, StringField, SelectField, FormField, IntegerField

app = Flask(__name__)
app.secret_key = 'TEST'
DATABASE = './db/database.db'

FORMATOS_DE_EXCEL = ['xls', 'xlsx', 'xlsm', 'xlsb', 'odf']
MENSAJE_NOMBRE_INVALIDO = 'Nombre de tabla o columna no válido.\nEl nombre solo puede contener letras del alfabeto español (incluyendo letras con tilde y Ñ) y guion bajo (_)'

def get_db():
	db = getattr(g, '_database', None)
	if db is None:
		try:
			db = g._database = sqlite3.connect(DATABASE)
		except:
			os.makedirs("./db", exist_ok=True)
			db = g._database = sqlite3.connect(DATABASE)
	db.row_factory = sqlite3.Row
	return db

@app.teardown_appcontext
def close_connection(exception):
	db = getattr(g, '_database', None)
	if db is not None:
		db.close()

def query_db(query, args=(), one=False):
	cur = get_db().execute(query, args)
	rv = cur.fetchall()
	cur.close()
	return (rv[0] if rv else None) if one else rv


def es_nombre_valido(nombre):
	return re.compile(r'^[A-z0-9ÁÉÍÓÚÜÑáéíóúüñ_]+$').search(nombre) != None

def comprobar_validez_de_nombre(nombre):
	if not es_nombre_valido(nombre):
		raise Exception(MENSAJE_NOMBRE_INVALIDO)

def obtener_nombres_de_tablas():
	nombres = []
	for tabla in query_db("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"):
		nombres.append(tabla['name'])
	return nombres

def obtener_nombres_de_columnas(nombre_de_tabla):
	comprobar_validez_de_nombre(nombre_de_tabla)
	nombres = []
	for columna in query_db(f"PRAGMA table_info({ nombre_de_tabla });"):
		nombres.append(columna['name'])
	return nombres

def obtener_tipos_de_datos_de_columnas(nombre_de_tabla):
	comprobar_validez_de_nombre(nombre_de_tabla)
	nombres = []
	for columna in query_db(f"PRAGMA table_info({ nombre_de_tabla });"):
		nombres.append(columna['type'])
	return nombres

def obtener_cantidad_de_filas_de_tabla(nombre_de_tabla):
	comprobar_validez_de_nombre(nombre_de_tabla)
	cantidad_de_filas = query_db(f"SELECT count(*) AS cantidad_de_filas FROM {nombre_de_tabla};")[0]['cantidad_de_filas']
	return cantidad_de_filas

def obtener_filas_de_tabla(nombre_de_tabla, limite=30, offset=0):
	comprobar_validez_de_nombre(nombre_de_tabla)
	filas = query_db(f"SELECT * FROM {nombre_de_tabla} LIMIT {int(limite)} OFFSET {int(offset)};")
	filas = [tuple(fila) for fila in filas]
	return filas

class Columna(FlaskForm):
	nombre = StringField('Nombre')
	tipo_de_datos = SelectField('Tipo de datos', choices=[
		('INTEGER', 'Numéricos (enteros)'),
		('REAL', 'Numéricos (decimales)'),
		('TEXT', 'Categóricos'),
		('TIMESTAMP', 'Fechas')
	])

class Columnas(FlaskForm):
	columnas = FieldList(FormField(Columna), min_entries=1)

def obtener_media(nombre_de_tabla, nombre_de_columna):
	comprobar_validez_de_nombre(nombre_de_tabla)
	comprobar_validez_de_nombre(nombre_de_columna)
	media = query_db(f"SELECT avg({nombre_de_columna}) AS media FROM {nombre_de_tabla};")[0]['media']
	return media

def obtener_minimo(nombre_de_tabla, nombre_de_columna):
	comprobar_validez_de_nombre(nombre_de_tabla)
	comprobar_validez_de_nombre(nombre_de_columna)
	minimo = query_db(f"SELECT min({nombre_de_columna}) AS minimo FROM {nombre_de_tabla};")[0]['minimo']
	return minimo

def obtener_maximo(nombre_de_tabla, nombre_de_columna):
	comprobar_validez_de_nombre(nombre_de_tabla)
	comprobar_validez_de_nombre(nombre_de_columna)
	maximo = query_db(f"SELECT max({nombre_de_columna}) AS maximo FROM {nombre_de_tabla};")[0]['maximo']
	return maximo

def obtener_conteo(nombre_de_tabla, nombre_de_columna):
	comprobar_validez_de_nombre(nombre_de_tabla)
	comprobar_validez_de_nombre(nombre_de_columna)
	conteos = query_db(f"SELECT {nombre_de_columna} AS categoria, count({nombre_de_columna}) AS conteo FROM {nombre_de_tabla} GROUP BY {nombre_de_columna};")
	conteos = [{conteo['categoria']: conteo['conteo']} for conteo in conteos]
	return conteos

@app.route('/subir-archivo', methods=["GET", "POST"])
def subir_archivo():

	if request.method == 'POST':

		nombre_de_tabla = request.form['nombre']
		comprobar_validez_de_nombre(nombre_de_tabla)

		if request.files:
			archivo = request.files['archivo']
			ext = archivo.filename.rsplit(".", 1)[1]
			db = get_db()
			header = 0 if 'con-nombre-de-columnas' in request.form else None

			if ext.lower() == 'csv':
				df = pd.read_csv(request.files.get('archivo'), header = header)

			if ext.lower() in FORMATOS_DE_EXCEL:
				df = pd.read_excel(request.files.get('archivo'), header = header)

			df = df.apply(lambda col: pd.to_datetime(col, errors='ignore', dayfirst=True)
				if col.dtypes == object
				else col,
				axis=0
			)

			df.to_sql(nombre_de_tabla, db, if_exists='replace', index=False)

			return redirect(url_for('mostrar_tabla', tabla=nombre_de_tabla))

	return render_template("subir-archivo.html")

@app.route('/modificar-columnas', methods=["GET", "POST"])
def modificar_columnas():

	if request.method == 'GET':
		nombre_de_tabla = request.args.get('tabla')
		comprobar_validez_de_nombre(nombre_de_tabla)

		nombres_de_columnas=obtener_nombres_de_columnas(nombre_de_tabla)
		tipos_de_datos_de_columnas=obtener_tipos_de_datos_de_columnas(nombre_de_tabla)
		numero_de_columnas=len(nombres_de_columnas)

		cols = [{'nombre': nombres_de_columnas[i]} for i in range(numero_de_columnas)]

		form = Columnas(columnas=cols)
		for i in range(len(cols)):
			form.columnas[i]['tipo_de_datos'].data = tipos_de_datos_de_columnas[i]

		return render_template(
			"modificar-columnas.html",
			form=form,
			numero_de_columnas=len(nombres_de_columnas),
			nombre_de_tabla=nombre_de_tabla
		)


	if request.method == 'POST':
		nombre_de_tabla = request.form['nombre_de_tabla']
		comprobar_validez_de_nombre(nombre_de_tabla)
		nombres_de_columnas=obtener_nombres_de_columnas(nombre_de_tabla)

		get_db().execute(f'''CREATE TABLE _nueva_{ nombre_de_tabla }(
			{', '.join(
				[request.form[f'columnas-{i}-nombre'] + ' ' + request.form[f'columnas-{i}-tipo_de_datos'] for i in range(len(nombres_de_columnas))]
			)}
		);''')
		get_db().execute(f'INSERT INTO _nueva_{ nombre_de_tabla } SELECT * FROM { nombre_de_tabla };')
		get_db().execute(f'DROP TABLE { nombre_de_tabla };')
		get_db().execute(f'ALTER TABLE _nueva_{ nombre_de_tabla } RENAME TO { nombre_de_tabla };')
		get_db().commit()

	return redirect(url_for('mostrar_tabla', tabla=nombre_de_tabla))


@app.route('/mostrar-tabla/<tabla>', defaults={'limite':30, 'offset':0}, methods=["GET"])
@app.route('/mostrar-tabla/<tabla>/<limite>', defaults={'offset':0}, methods=['GET'])
@app.route('/mostrar-tabla/<tabla>/<limite>/<offset>', methods=['GET'])
def mostrar_tabla(tabla, limite, offset):
	comprobar_validez_de_nombre(tabla)
	nombres_de_columnas	= obtener_nombres_de_columnas(tabla)

	cantidad_de_filas = obtener_cantidad_de_filas_de_tabla(tabla)
	grupos_de_filas = []
	offset_actual = 0
	tamano_de_grupo = int(limite)
	numero_de_grupo = 1
	while offset_actual < cantidad_de_filas:
		grupos_de_filas.append({
			'numero_de_grupo': numero_de_grupo,
			'tamano_de_grupo': tamano_de_grupo,
			'offset_actual': offset_actual,
			})
		numero_de_grupo += 1
		offset_actual += tamano_de_grupo

	return render_template(
		"mostrar-tabla.html",
		nombre_de_tabla=tabla,
		nombres_de_columnas=nombres_de_columnas,
		limite=limite,
		offset=offset,
		grupos_de_filas=grupos_de_filas,
	)


@app.route('/api/tablas', methods=['GET'])
def api_tablas():
	nombres_de_tablas = obtener_nombres_de_tablas()
	return jsonify(nombres_de_tablas)

@app.route('/api/columnas/<tabla>', methods=['GET'])
def api_columnas(tabla):
	comprobar_validez_de_nombre(tabla)
	nombres_de_columnas = obtener_nombres_de_columnas(tabla)
	return jsonify(nombres_de_columnas)

@app.route('/api/tipos-de-datos/<tabla>', methods=['GET'])
def api_tipos_de_datos(tabla):
	comprobar_validez_de_nombre(tabla)
	nombres_de_columnas = obtener_nombres_de_columnas(tabla)
	tipos_de_datos_de_columnas = obtener_tipos_de_datos_de_columnas(tabla)
	tipos_de_datos_de_columnas = [{nombres_de_columnas[i]: tipos_de_datos_de_columnas[i]} for i in range(len(nombres_de_columnas))]
	return jsonify(tipos_de_datos_de_columnas)

@app.route('/api/cantidad-de-filas/<tabla>', methods=['GET'])
def api_cantidad_de_filas(tabla):
	comprobar_validez_de_nombre(tabla)
	cantidad_de_filas = obtener_cantidad_de_filas_de_tabla(tabla)
	return jsonify(cantidad_de_filas)

@app.route('/api/filas/<tabla>', defaults={'limite':30, 'offset':0}, methods=['GET'])
@app.route('/api/filas/<tabla>/<limite>', defaults={'offset':0}, methods=['GET'])
@app.route('/api/filas/<tabla>/<limite>/<offset>', methods=['GET'])
def api_filas(tabla, limite, offset):
	comprobar_validez_de_nombre(tabla)
	filas = obtener_filas_de_tabla(tabla, limite=limite, offset=offset)
	return jsonify(filas)

@app.route('/api/media/<tabla>/<columna>', methods=['GET'])
def api_media(tabla, columna):
	comprobar_validez_de_nombre(tabla)
	comprobar_validez_de_nombre(columna)
	media = obtener_media(tabla, columna)
	return jsonify(media)

@app.route('/api/minimo/<tabla>/<columna>', methods=['GET'])
def api_minimo(tabla, columna):
	comprobar_validez_de_nombre(tabla)
	comprobar_validez_de_nombre(columna)
	minimo = obtener_minimo(tabla, columna)
	return jsonify(minimo)

@app.route('/api/maximo/<tabla>/<columna>', methods=['GET'])
def api_maximo(tabla, columna):
	comprobar_validez_de_nombre(tabla)
	comprobar_validez_de_nombre(columna)
	maximo = obtener_maximo(tabla, columna)
	return jsonify(maximo)

@app.route('/api/conteo/<tabla>/<columna>', methods=['GET'])
def api_conteo(tabla, columna):
	comprobar_validez_de_nombre(tabla)
	comprobar_validez_de_nombre(columna)
	conteo = obtener_conteo(tabla, columna)
	return jsonify(conteo)


if __name__ == '__main__':
	app.run(debug=True)
