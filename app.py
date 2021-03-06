from flask import Flask, render_template, request, g, jsonify, redirect, url_for
import pandas as pd
import sqlite3
import re
import os
import json
from scipy.stats import pearsonr
from flask_wtf import FlaskForm
from wtforms import FieldList, StringField, SelectField, FormField, IntegerField

app = Flask(__name__)
app.secret_key = 'TEST'
DATABASE = './db/database.db'

FORMATOS_DE_EXCEL = ['xls', 'xlsx', 'xlsm', 'xlsb', 'odf']
MENSAJE_NOMBRE_INVALIDO = 'Nombre de tabla o columna no válido.\nEl nombre solo puede contener letras del alfabeto español (incluyendo letras con tilde y Ñ) y guion bajo (_).'
MENSAJE_OPERACION_FALLIDA_VALORES_NO_NUMERICOS = 'No se pudo realizar la operación, posiblemente porque la columna contenía valores no numéricos.'

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
	return re.compile(r'^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ_]+$').search(nombre) != None

def comprobar_validez_de_nombre(nombre):
	if not es_nombre_valido(nombre):
		raise Exception(MENSAJE_NOMBRE_INVALIDO)

def obtener_nombres_de_tablas():
	nombres = []
	for tabla in query_db("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"):
		nombres.append(tabla['name'])
	return nombres

def eliminar_tabla(nombre_de_tabla):
	comprobar_validez_de_nombre(nombre_de_tabla)
	get_db().execute(f'DROP TABLE "{ nombre_de_tabla }";')
	get_db().commit()

def obtener_nombres_de_columnas(nombre_de_tabla):
	comprobar_validez_de_nombre(nombre_de_tabla)
	nombres = []
	for columna in query_db(f'PRAGMA table_info("{ nombre_de_tabla }");'):
		nombres.append(columna['name'])
	return nombres

def obtener_tipos_de_datos_de_columnas(nombre_de_tabla):
	comprobar_validez_de_nombre(nombre_de_tabla)
	nombres = []
	for columna in query_db(f'PRAGMA table_info("{ nombre_de_tabla }");'):
		nombres.append(columna['type'])
	return nombres

def obtener_tipo_de_datos_de_columna(nombre_de_tabla, nombre_de_columna):
	comprobar_validez_de_nombre(nombre_de_tabla)
	comprobar_validez_de_nombre(nombre_de_columna)
	nombres = obtener_nombres_de_columnas(nombre_de_tabla)
	tipos_de_datos = obtener_tipos_de_datos_de_columnas(nombre_de_tabla)
	for i in range(len(nombres)):
		if nombres[i] == nombre_de_columna:
			return tipos_de_datos[i]
	raise Exception('No se encontró la columna especificada en la tabla especificada.')

def obtener_cantidad_de_filas_de_tabla(nombre_de_tabla):
	comprobar_validez_de_nombre(nombre_de_tabla)
	cantidad_de_filas = query_db(f'SELECT count(*) AS cantidad_de_filas FROM "{nombre_de_tabla}";')[0]['cantidad_de_filas']
	return cantidad_de_filas

def obtener_filas_de_tabla(nombre_de_tabla, limite=30, offset=0):
	comprobar_validez_de_nombre(nombre_de_tabla)
	filas = query_db(f'SELECT * FROM "{nombre_de_tabla}" LIMIT {int(limite)} OFFSET {int(offset)};')
	filas = [tuple(fila) for fila in filas]
	return filas

def obtener_valores_nulos_por_columna(nombre_de_tabla):
	comprobar_validez_de_nombre(nombre_de_tabla)
	df = pd.read_sql(f'SELECT * FROM "{nombre_de_tabla}"', con=get_db())
	return df.isna().sum().to_dict()

def obtener_indices_de_filas_con_valores_nulos(nombre_de_tabla):
	comprobar_validez_de_nombre(nombre_de_tabla)
	df = pd.read_sql(f'SELECT * FROM "{nombre_de_tabla}"', con=get_db())
	valores_nulos_por_fila = df.isna().sum(axis=1).to_dict()
	indices_de_filas_con_valores_nulos = []
	for fila, cantidad_de_valores_nulos in valores_nulos_por_fila.items():
		if cantidad_de_valores_nulos > 0:
			indices_de_filas_con_valores_nulos.append(fila)
	return indices_de_filas_con_valores_nulos

def obtener_tabla_como_dataframe(nombre_de_tabla):
	comprobar_validez_de_nombre(nombre_de_tabla)
	df = pd.read_sql(f'SELECT * FROM "{nombre_de_tabla}"', con=get_db())
	df = df.apply(
		lambda col: pd.to_datetime(col, errors='ignore', dayfirst=True)
		if obtener_tipo_de_datos_de_columna(nombre_de_tabla, col.name) == 'TIMESTAMP'
		else col,
	)
	return df

def obtener_columna_de_tabla_como_series(nombre_de_tabla, nombre_de_columna):
	comprobar_validez_de_nombre(nombre_de_tabla)
	comprobar_validez_de_nombre(nombre_de_columna)
	df = pd.read_sql(f'SELECT "{nombre_de_columna}" FROM "{nombre_de_tabla}"', con=get_db())
	df = df.apply(lambda col: pd.to_datetime(col, errors='ignore', dayfirst=True)
		if obtener_tipo_de_datos_de_columna(nombre_de_tabla, nombre_de_columna) == 'TIMESTAMP'
		else col,
	)
	columna = df[nombre_de_columna]
	return columna

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
	media = query_db(f'SELECT avg("{nombre_de_columna}") AS media FROM "{nombre_de_tabla}";')[0]['media']
	return media

def obtener_desviacion_estandar(nombre_de_tabla, nombre_de_columna):
	comprobar_validez_de_nombre(nombre_de_tabla)
	comprobar_validez_de_nombre(nombre_de_columna)
	columna = obtener_columna_de_tabla_como_series(nombre_de_tabla, nombre_de_columna)
	try:
		desviacion_estandar = columna.std()
		return desviacion_estandar
	except:
		raise Exception(MENSAJE_OPERACION_FALLIDA_VALORES_NO_NUMERICOS)

def obtener_minimo(nombre_de_tabla, nombre_de_columna):
	comprobar_validez_de_nombre(nombre_de_tabla)
	comprobar_validez_de_nombre(nombre_de_columna)
	minimo = query_db(f'SELECT min("{nombre_de_columna}") AS minimo FROM "{nombre_de_tabla}";')[0]['minimo']
	return minimo

def obtener_maximo(nombre_de_tabla, nombre_de_columna):
	comprobar_validez_de_nombre(nombre_de_tabla)
	comprobar_validez_de_nombre(nombre_de_columna)
	maximo = query_db(f'SELECT max("{nombre_de_columna}") AS maximo FROM "{nombre_de_tabla}";')[0]['maximo']
	return maximo

def obtener_conteo(nombre_de_tabla, nombre_de_columna):
	comprobar_validez_de_nombre(nombre_de_tabla)
	comprobar_validez_de_nombre(nombre_de_columna)
	conteos = query_db(f'SELECT "{nombre_de_columna}" AS categoria, count("{nombre_de_columna}") AS conteo FROM "{nombre_de_tabla}" GROUP BY "{nombre_de_columna}";')
	conteos = {conteo['categoria']: conteo['conteo'] for conteo in conteos}
	try:
		del conteos[None]
	except KeyError:
		pass
	return conteos

def obtener_moda(nombre_de_tabla, nombre_de_columna):
	comprobar_validez_de_nombre(nombre_de_tabla)
	comprobar_validez_de_nombre(nombre_de_columna)
	conteo = obtener_conteo(nombre_de_tabla, nombre_de_columna)
	una_moda = max(conteo, key=conteo.get)
	todas_las_modas = []
	for nivel in conteo:
		if conteo[nivel] == conteo[una_moda]:
			todas_las_modas.append(nivel)
	return todas_las_modas

def obtener_mediana(nombre_de_tabla, nombre_de_columna):
	comprobar_validez_de_nombre(nombre_de_tabla)
	comprobar_validez_de_nombre(nombre_de_columna)
	columna = obtener_columna_de_tabla_como_series(nombre_de_tabla, nombre_de_columna)
	try:
		mediana = columna.quantile([.50])
		if obtener_tipo_de_datos_de_columna(nombre_de_tabla, nombre_de_columna) == 'TIMESTAMP':
			mediana = mediana.dt.strftime('%Y-%m-%d %H:%M:%S')
		return mediana.to_dict()[0.5]
	except:
		raise Exception(MENSAJE_OPERACION_FALLIDA_VALORES_NO_NUMERICOS)

def obtener_quintiles(nombre_de_tabla, nombre_de_columna):
	comprobar_validez_de_nombre(nombre_de_tabla)
	comprobar_validez_de_nombre(nombre_de_columna)
	columna = obtener_columna_de_tabla_como_series(nombre_de_tabla, nombre_de_columna)
	try:
		quintiles = columna.quantile([.20, .40, .60, .80])
		if obtener_tipo_de_datos_de_columna(nombre_de_tabla, nombre_de_columna) == 'TIMESTAMP':
			quintiles = quintiles.dt.strftime('%Y-%m-%d %H:%M:%S')
		return quintiles.to_dict()
	except:
		raise Exception(MENSAJE_OPERACION_FALLIDA_VALORES_NO_NUMERICOS)

def obtener_cuartiles(nombre_de_tabla, nombre_de_columna):
	comprobar_validez_de_nombre(nombre_de_tabla)
	comprobar_validez_de_nombre(nombre_de_columna)
	columna = obtener_columna_de_tabla_como_series(nombre_de_tabla, nombre_de_columna)
	try:
		cuartiles = columna.quantile([.25, .50, .75])
		if obtener_tipo_de_datos_de_columna(nombre_de_tabla, nombre_de_columna) == 'TIMESTAMP':
			cuartiles = cuartiles.dt.strftime('%Y-%m-%d %H:%M:%S')
		return cuartiles.to_dict()
	except:
		raise Exception(MENSAJE_OPERACION_FALLIDA_VALORES_NO_NUMERICOS)

def obtener_correlaciones_de_tabla(nombre_de_tabla):
	comprobar_validez_de_nombre(nombre_de_tabla)
	tabla = obtener_tabla_como_dataframe(nombre_de_tabla)
	tabla = tabla.loc[:, tabla.columns != 'idx']
	return tabla.corr(method=lambda x, y: pearsonr(x, y)[0])

def obtener_valores_p_de_correlaciones_de_tabla(nombre_de_tabla):
	comprobar_validez_de_nombre(nombre_de_tabla)
	tabla = obtener_tabla_como_dataframe(nombre_de_tabla)
	tabla = tabla.loc[:, tabla.columns != 'idx']
	return tabla.corr(method=lambda x, y: pearsonr(x, y)[1])

def obtener_correlacion_de_columnas(nombre_de_tabla, nombre_de_columna_1, nombre_de_columna_2):
	comprobar_validez_de_nombre(nombre_de_tabla)
	comprobar_validez_de_nombre(nombre_de_columna_1)
	comprobar_validez_de_nombre(nombre_de_columna_2)
	columna_1 = obtener_columna_de_tabla_como_series(nombre_de_tabla, nombre_de_columna_1)
	columna_2 = obtener_columna_de_tabla_como_series(nombre_de_tabla, nombre_de_columna_2)
	r, valor_p = columna_1.corr(columna_2, method=pearsonr)
	return {'r': r, 'valor_p': valor_p}

def obtener_resumen_de_columna(nombre_de_tabla, nombre_de_columna):
	comprobar_validez_de_nombre(nombre_de_tabla)
	comprobar_validez_de_nombre(nombre_de_columna)
	tipo_de_datos = obtener_tipo_de_datos_de_columna(nombre_de_tabla, nombre_de_columna)
	columna = obtener_columna_de_tabla_como_series(nombre_de_tabla, nombre_de_columna)

	if tipo_de_datos == 'INTEGER' or tipo_de_datos == 'REAL':
		media = obtener_media(nombre_de_tabla, nombre_de_columna)
		desviacion_estandar = columna.std()
		minimo = obtener_minimo(nombre_de_tabla, nombre_de_columna)
		maximo = obtener_maximo(nombre_de_tabla, nombre_de_columna)
		mediana = columna.quantile([.50])
		mediana = mediana.to_dict()[0.5]
		quintiles = columna.quantile([.20, .40, .60, .80])
		quintiles = quintiles.to_dict()
		cuartiles = columna.quantile([.25, .50, .75])
		cuartiles = cuartiles.to_dict()
		return {
			'media': media,
			'desviacion_estandar': desviacion_estandar,
			'minimo': minimo,
			'maximo': maximo,
			'mediana': mediana,
			'quintiles': quintiles,
			'cuartiles': cuartiles,
		}

	if tipo_de_datos == 'TIMESTAMP':
		minimo = obtener_minimo(nombre_de_tabla, nombre_de_columna)
		maximo = obtener_maximo(nombre_de_tabla, nombre_de_columna)
		mediana = columna.quantile([.50])
		mediana = mediana.dt.strftime('%Y-%m-%d %H:%M:%S')
		mediana = mediana.to_dict()[0.5]
		quintiles = columna.quantile([.20, .40, .60, .80])
		quintiles = quintiles.dt.strftime('%Y-%m-%d %H:%M:%S')
		quintiles = quintiles.to_dict()
		cuartiles = columna.quantile([.25, .50, .75])
		cuartiles = cuartiles.dt.strftime('%Y-%m-%d %H:%M:%S')
		cuartiles = cuartiles.to_dict()
		return {
			'minimo': minimo,
			'maximo': maximo,
			'mediana': mediana,
			'quintiles': quintiles,
			'cuartiles': cuartiles,
		}

	if tipo_de_datos == 'TEXT':
		conteos = obtener_conteo(nombre_de_tabla, nombre_de_columna)
		moda = obtener_moda(nombre_de_tabla, nombre_de_columna)
		return {
			'conteo': conteos,
			'moda': moda,
		}

def obtener_resumen_de_2_columnas(nombre_de_tabla, nombre_de_columna_1, nombre_de_columna_2):
	comprobar_validez_de_nombre(nombre_de_tabla)
	comprobar_validez_de_nombre(nombre_de_columna_1)
	comprobar_validez_de_nombre(nombre_de_columna_2)
	resumen = {}
	resumen['columnas'] = {
		nombre_de_columna_1: obtener_resumen_de_columna(nombre_de_tabla, nombre_de_columna_1),
		nombre_de_columna_2: obtener_resumen_de_columna(nombre_de_tabla, nombre_de_columna_2),	
	}
	tipo_de_datos_de_columna_1 = obtener_tipo_de_datos_de_columna(nombre_de_tabla, nombre_de_columna_1)
	columna_1_es_numerica = tipo_de_datos_de_columna_1 == 'INTEGER' or tipo_de_datos_de_columna_1 == 'REAL'
	tipo_de_datos_de_columna_2 = obtener_tipo_de_datos_de_columna(nombre_de_tabla, nombre_de_columna_2)
	columna_2_es_numerica = tipo_de_datos_de_columna_2 == 'INTEGER' or tipo_de_datos_de_columna_2 == 'REAL'
	if columna_1_es_numerica and columna_2_es_numerica:
		resumen['correlacion'] = obtener_correlacion_de_columnas(nombre_de_tabla, nombre_de_columna_1, nombre_de_columna_2)

	return resumen

def obtener_resumen_de_tabla(nombre_de_tabla):
	comprobar_validez_de_nombre(nombre_de_tabla)
	resumen = {}
	resumen['columnas'] = {}
	for nombre_de_columna in obtener_nombres_de_columnas(nombre_de_tabla):
		resumen['columnas'][nombre_de_columna] = obtener_resumen_de_columna(nombre_de_tabla, nombre_de_columna)
	resumen['correlaciones'] = {}
	correlaciones = obtener_correlaciones_de_tabla(nombre_de_tabla)
	corr_json = correlaciones.to_json()
	resumen['correlaciones']['r'] = json.loads(corr_json)
	valores_p = obtener_valores_p_de_correlaciones_de_tabla(nombre_de_tabla)
	valores_p_json = valores_p.to_json()
	resumen['correlaciones']['valores_p'] = json.loads(valores_p_json)
	return resumen


# Rutas

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
				df = pd.read_csv(request.files.get('archivo'), header = header, prefix='col_')

			if ext.lower() in FORMATOS_DE_EXCEL:
				df = pd.read_excel(request.files.get('archivo'), header = header, prefix='col_')

			df = df.apply(lambda col: pd.to_datetime(col, errors='ignore', dayfirst=True)
				if col.dtypes == object
				else col,
				axis=0
			)

			caracteres_no_validos = re.compile(r'[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ_]')
			nombres_de_columnas_validos = {
				viejo_nombre: re.sub(caracteres_no_validos, '', viejo_nombre.replace(' ', '_')) for viejo_nombre in df.columns
				}
			df.rename(nombres_de_columnas_validos, axis=1, inplace=True)

			df.to_sql(nombre_de_tabla, db, if_exists='replace', index=True, index_label='idx')

			return redirect(url_for('mostrar_tabla', tabla=nombre_de_tabla))

	return render_template("subir-archivo.html")

@app.route('/modificar-columnas/<tabla>', methods=["GET"])
def modificar_columnas_GET(tabla):
	nombre_de_tabla = tabla
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

@app.route('/modificar-columnas/modificar-columnas', methods=["POST"])
def modificar_columnas_POST():
	nombre_de_tabla = request.form['nombre_de_tabla']
	comprobar_validez_de_nombre(nombre_de_tabla)
	nombres_de_columnas=obtener_nombres_de_columnas(nombre_de_tabla)

	for i in range(len(nombres_de_columnas)):
		comprobar_validez_de_nombre(request.form[f'columnas-{i}-nombre'])

	get_db().execute(f'''CREATE TABLE "_nueva_{ nombre_de_tabla }"("{
		', "'.join(
			[request.form[f'columnas-{i}-nombre'] + '" ' + request.form[f'columnas-{i}-tipo_de_datos'] for i in range(len(nombres_de_columnas))]
		)
	});''')
	get_db().execute(f'INSERT INTO "_nueva_{ nombre_de_tabla }" SELECT * FROM "{ nombre_de_tabla }";')
	get_db().execute(f'DROP TABLE "{ nombre_de_tabla }";')
	get_db().execute(f'ALTER TABLE "_nueva_{ nombre_de_tabla }" RENAME TO "{ nombre_de_tabla }";')
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

@app.route('/api/eliminar-tabla/<tabla>', methods=['GET'])
def api_eliminar_tabla(tabla):
	comprobar_validez_de_nombre(tabla)
	eliminar_tabla(tabla)
	return redirect(url_for('api_tablas'))	

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
	tipos_de_datos_de_columnas = [[nombres_de_columnas[i], tipos_de_datos_de_columnas[i]] for i in range(len(nombres_de_columnas))]
	return jsonify(tipos_de_datos_de_columnas)

@app.route('/api/tipo-de-datos/<tabla>/<columna>', methods=['GET'])
def api_tipo_de_datos_1_columna(tabla, columna):
	comprobar_validez_de_nombre(tabla)
	comprobar_validez_de_nombre(columna)
	tipo_de_datos = obtener_tipo_de_datos_de_columna(tabla, columna)
	return jsonify(tipo_de_datos)

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

@app.route('/api/valores-nulos-por-columna/<tabla>', methods=['GET'])
def api_valores_nulos_por_columna(tabla):
	comprobar_validez_de_nombre(tabla)
	valores_nulos_por_columna = obtener_valores_nulos_por_columna(tabla)
	return jsonify(valores_nulos_por_columna)

@app.route('/api/indices-de-filas-con-valores-nulos/<tabla>', methods=['GET'])
def api_indices_de_filas_con_valores_nulos(tabla):
	comprobar_validez_de_nombre(tabla)
	indices_de_filas_con_valores_nulos = obtener_indices_de_filas_con_valores_nulos(tabla)
	return jsonify(indices_de_filas_con_valores_nulos)

@app.route('/api/media/<tabla>/<columna>', methods=['GET'])
def api_media(tabla, columna):
	comprobar_validez_de_nombre(tabla)
	comprobar_validez_de_nombre(columna)
	media = obtener_media(tabla, columna)
	return jsonify(media)

@app.route('/api/desviacion-estandar/<tabla>/<columna>', methods=['GET'])
def api_desviacion_estandar(tabla, columna):
	comprobar_validez_de_nombre(tabla)
	comprobar_validez_de_nombre(columna)
	desviacion_estandar = obtener_desviacion_estandar(tabla, columna)
	return jsonify(desviacion_estandar)

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

@app.route('/api/moda/<tabla>/<columna>', methods=['GET'])
def api_moda(tabla, columna):
	comprobar_validez_de_nombre(tabla)
	comprobar_validez_de_nombre(columna)
	moda = obtener_moda(tabla, columna)
	return jsonify(moda)

@app.route('/api/mediana/<tabla>/<columna>', methods=['GET'])
def api_mediana(tabla, columna):
	comprobar_validez_de_nombre(tabla)
	comprobar_validez_de_nombre(columna)
	mediana = obtener_mediana(tabla, columna)
	return jsonify(mediana)

@app.route('/api/quintiles/<tabla>/<columna>', methods=['GET'])
def api_quintiles(tabla, columna):
	comprobar_validez_de_nombre(tabla)
	comprobar_validez_de_nombre(columna)
	quintiles = obtener_quintiles(tabla, columna)
	return jsonify(quintiles)

@app.route('/api/cuartiles/<tabla>/<columna>', methods=['GET'])
def api_cuartiles(tabla, columna):
	comprobar_validez_de_nombre(tabla)
	comprobar_validez_de_nombre(columna)
	cuartiles = obtener_cuartiles(tabla, columna)
	return jsonify(cuartiles)

@app.route('/api/correlaciones-de-tabla/<tabla>', methods=['GET'])
def api_tabla_de_correlaciones(tabla):
	comprobar_validez_de_nombre(tabla)
	correlaciones = obtener_correlaciones_de_tabla(tabla)
	corr_json = correlaciones.to_json()
	return jsonify(json.loads(corr_json))

@app.route('/api/valores-p-de-correlaciones-de-tabla/<tabla>', methods=['GET'])
def api_valores_p_tabla_de_correlaciones(tabla):
	comprobar_validez_de_nombre(tabla)
	valores_p = obtener_valores_p_de_correlaciones_de_tabla(tabla)
	valores_p_json = valores_p.to_json()
	return jsonify(json.loads(valores_p_json))

@app.route('/api/correlacion/<tabla>/<columna1>/<columna2>', methods=['GET'])
def api_correlacion(tabla, columna1, columna2):
	comprobar_validez_de_nombre(tabla)
	comprobar_validez_de_nombre(columna1)
	comprobar_validez_de_nombre(columna2)
	correlacion = obtener_correlacion_de_columnas(tabla, columna1, columna2)
	return jsonify(correlacion)

@app.route('/api/resumen-de-columna/<tabla>/<columna>', methods=['GET'])
def api_resumen_columna(tabla, columna):
	comprobar_validez_de_nombre(tabla)
	comprobar_validez_de_nombre(columna)
	resumen = obtener_resumen_de_columna(tabla, columna)
	return jsonify(resumen)

@app.route('/api/resumen-de-2-columnas/<tabla>/<columna1>/<columna2>', methods=['GET'])
def api_resumen_2_columnas(tabla, columna1, columna2):
	comprobar_validez_de_nombre(tabla)
	comprobar_validez_de_nombre(columna1)
	comprobar_validez_de_nombre(columna2)
	resumen = obtener_resumen_de_2_columnas(tabla, columna1, columna2)
	return jsonify(resumen)

@app.route('/api/resumen-de-tabla/<tabla>', methods=['GET'])
def api_resumen_tabla(tabla):
	comprobar_validez_de_nombre(tabla)
	resumen = obtener_resumen_de_tabla(tabla)
	return jsonify(resumen)

if __name__ == '__main__':
	app.run(debug=True)
