from flask import Flask, render_template, request, g
import pandas as pd
import sqlite3
import re

app = Flask(__name__)
DATABASE = './db/database.db'

FORMATOS_DE_EXCEL = ['xls', 'xlsx', 'xlsm', 'xlsb', 'odf']
MENSAJE_NOMBRE_INVALIDO = 'Nombre de tabla o columna no válido.\nEl nombre solo puede contener letras del alfabeto español (incluyendo letras con tilde y Ñ) y guion bajo (_)'

def get_db():
	db = getattr(g, '_database', None)
	if db is None:
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
	conteo = query_db(f"SELECT count({nombre_de_columna}) AS conteo FROM {nombre_de_tabla};")[0]['conteo']
	return conteo


@app.route('/subir-archivo', methods=["GET", "POST"])
def subir_archivo():

	if request.method == 'POST':

		comprobar_validez_de_nombre(request.form['nombre'])

		if request.files:
			archivo = request.files['archivo']
			ext = archivo.filename.rsplit(".", 1)[1]
			db = get_db()
			header = 0 if 'con-nombre-de-columnas' in request.form else None

			if ext.lower() == 'csv':
				df = pd.read_csv(request.files.get('archivo'), header = header)

			if ext.lower() in FORMATOS_DE_EXCEL:
				df = pd.read_excel(request.files.get('archivo'))

			df.to_sql(request.form['nombre'], db, if_exists='replace', index=False)

	return render_template("subir-archivo.html")


if __name__ == '__main__':
	app.run(debug=True)
