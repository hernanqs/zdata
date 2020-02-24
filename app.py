from flask import Flask, render_template, request
app = Flask(__name__)


@app.route('/subir-archivo', methods=["GET", "POST"])
def subir_archivo():

	if request.method == 'POST':
		if request.files:
			archivo = request.files['archivo']
			print(archivo)

	return render_template("subir-archivo.html")


if __name__ == '__main__':
	app.run(debug=True)
