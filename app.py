from flask import Flask, render_template, request
import io
import pandas as pd
app = Flask(__name__)


import sqlite3
from flask import g

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


@app.route('/subir-archivo', methods=["GET", "POST"])
def subir_archivo():

	if request.method == 'POST':
		if request.files:
			archivo = request.files['archivo']
			stream = io.StringIO(archivo.stream.read().decode("UTF8"), newline=None)
			db = get_db()
			header = 0 if 'con-nombre-de-columnas' in request.form else None
			df = pd.read_csv(stream, header = header)
			df.to_sql(request.form['nombre'], db, if_exists='replace', index=False)

	return render_template("subir-archivo.html")


if __name__ == '__main__':
	app.run(debug=True)
