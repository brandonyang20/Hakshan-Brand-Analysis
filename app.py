import os

from flask import Flask, jsonify, render_template

from data_fetcher import get_data, read_analysis_section


def create_app() -> Flask:
    app = Flask(__name__)
    os.makedirs(os.path.join(os.path.dirname(__file__), "cache"), exist_ok=True)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/data")
    def api_data():
        try:
            data = get_data(force=False)
            return jsonify(data)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/refresh", methods=["POST"])
    def api_refresh():
        try:
            data = get_data(force=True)
            return jsonify(data)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/analysis/<section>")
    def api_analysis(section):
        content = read_analysis_section(section)
        if not content:
            return jsonify({"error": "Section not found"}), 404
        return jsonify({"section": section, "content": content})

    return app


app = create_app()


def setup_scheduler(flask_app: Flask):
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler(daemon=True)

        def daily_refresh():
            with flask_app.app_context():
                print("[scheduler] Running daily data refresh...")
                get_data(force=True)
                print("[scheduler] Daily refresh complete.")

        scheduler.add_job(daily_refresh, trigger="cron", hour=3, minute=0)
        scheduler.start()
        print("[scheduler] Daily refresh scheduled at 03:00.")
        return scheduler
    except ImportError:
        print("[scheduler] APScheduler not installed — scheduled refresh disabled.")
        return None


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    scheduler = setup_scheduler(app)
    try:
        app.run(debug=False, host="0.0.0.0", port=port, use_reloader=False)
    finally:
        if scheduler:
            scheduler.shutdown()
