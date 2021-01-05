from flask import Flask, render_template, request, send_from_directory
import db_funcs

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/robots.txt')
@app.route('/sitemap.xml')
def static_from_root():
    return send_from_directory(app.static_folder, request.path[1:])

# Everything static except tutor request.
@app.route('/home', methods=['POST', 'GET'])
def home():
    if request.method == "POST":
        db_funcs.requestTutoring(request.form)
    return render_template('home.html')

@app.route('/essay-editing')
def essay_editing():
    return render_template('essay-editing.html')\

@app.route('/resources')
def resources():
    return render_template('resources.html')

@app.route('/our-team')
def our_team():
    return render_template('our-team.html')

@app.route('/join-us')
def join_us():
    return render_template('join-us.html')

if __name__ == '__main__':
    app.run(debug=True)