from flask_restplus import Api, Resource, fields
from werkzeug.contrib.fixers import ProxyFix
from flask import Flask, url_for, jsonify
import probablepeople as pp
import json


app = Flask(__name__)
api = Api(app,
	      version='1.0', 
          title='Swagger Test Page for Party Typer', 
          description='Party Typer', 
          prefix="/v1",
          contact="john@swarmee.net",
          contact_url="www.swarmee.net"
         )
app.wsgi_app = ProxyFix(app.wsgi_app)

ns = api.namespace('partyType', description='Simple Party Type Identification')

partyTypeParser = ns.parser()
partyTypeParser.add_argument('partyName', type=str, help='partyName to determine Type For', location='form')

##### Using Probable Name to determine party type
@ns.route('/partyType')
class partyType(Resource):
    @ns.doc(parser=partyTypeParser)
    def post(self):
        args = partyTypeParser.parse_args()
        partyNameText = args['partyName']
        resp = pp.tag(partyNameText)
        type = resp[-1]
        if type in ['Person']:
          return jsonify(partyName=partyNameText,partyTypeConfidence='High',partyType=type)
        elif type in ['Corporation']:
          return jsonify(partyName=partyNameText,partyTypeConfidence='High',partyType=type)
        else: 
          return jsonify(partyName=partyNameText,partyTypeConfidence='Low',partyType='Person')
         


if __name__ == '__main__':
    app.run(debug=False)
