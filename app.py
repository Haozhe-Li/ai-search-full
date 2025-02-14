from flask import Flask, render_template, request, jsonify
from core.aisearch import AISearch
from core.test_response import get_sample_response
from core.suggestion import get_suggestion
import time
import os

is_dev = os.environ.get("DEV", 0)

app = Flask(__name__)
search = AISearch()


@app.route("/")
async def index():
    return render_template("index.html")

@app.route("/getsuggestion")
async def getsuggestion():
    language = request.args.get("language")
    return jsonify(get_suggestion(language))


@app.route("/search", methods=["POST"])
async def main():
    try:
        query = request.json["query"]
        mode = request.json["mode"]
        title = f"""# {query}\n\n------\n\n
"""
        footer = """\n\n------\n\n"""
        if query == "test":
            result = title + get_sample_response() + footer
            time.sleep(3)
            return jsonify({"result": result})
        if query == "longtest":
            result = title + get_sample_response() + footer
            time.sleep(10)
            return jsonify({"result": result})
        result = (
            await search.search(query)
            if mode == "universal"
            else await search.quick_search(query)
        )
        result = title + result["answer"] + footer
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"result": "Hi I'm Omni, but something went wrong! Could you please try again?"})


if __name__ == "__main__":
    if is_dev:
        app.run(debug=True)
    else:
        app.run()
