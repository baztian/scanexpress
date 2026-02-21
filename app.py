from flask import Flask, jsonify, render_template

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/scan")
def trigger_scan():
    return jsonify(
        {
            "status": "not_implemented",
            "message": "Scan trigger will be implemented next.",
        }
    ), 501


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
