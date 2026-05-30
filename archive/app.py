import json
import requests
from flask import Flask, render_template, request, flash, redirect, url_for
app = Flask(__name__)

@app.route('/')
def index():
    r = requests.get("http://ncaa-lacrosse.herokuapp.com/lacrosse.json?sql=select+Team%2C+sum%28%5BCaused+Turnovers%5D%29+as+total_caused_turnovers%2C+G%2C+sum%28cast%28%5BCaused+Turnovers%5D+as+float%29%29%2FG+as+per_game%0D%0Afrom+players+%0D%0Agroup+by+1%0D%0Aorder+by+4+desc+limit+15")
    results = r.json()['rows']
    return render_template('index.html', results=results)

@app.route('/caused-turnovers/<team>')
def caused_turnovers(team):
    team_slug = team.replace(" ","+")
    r = requests.get(f"http://ncaa-lacrosse.herokuapp.com/lacrosse.json?sql=select+Season%2C+Team%2C+%5BJersey+Number%5D%2C+%5BFull+Name%5D%2C+Year%2C+Position%2C+%5BGames+Played%5D%2C+%5BGames+Started%5D%2C+%5BCaused+Turnovers%5D%2C+%5BNCAA+id%5D+from+players+where+%22Team%22+%3D+%3Ap0+and+%5BCaused+Turnovers%5D+%3E+0+order+by+%5BCaused+Turnovers%5D+desc&p0={team_slug}")
    results = r.json()['rows']
    return render_template('caused_turnovers.html', results=results, team=team)

if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)

