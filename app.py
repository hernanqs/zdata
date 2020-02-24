from flask import Flask, render_template, request, g
import pandas as pd
import sqlite3

app = Flask(__name__)
DATABASE = './db/database.db'

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


FORMATOS_DE_EXCEL = ['xls', 'xlsx', 'xlsm', 'xlsb', 'odf']

@app.route('/subir-archivo', methods=["GET", "POST"])
def subir_archivo():

	if request.method == 'POST':
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
