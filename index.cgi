#!/usr/bin/python3
# encoding: utf-8


'''
 -- Web interface for generating Excel sheet.
 Fork of https://github.com/umeldt/darwinsheet


@author:     Pål Ellingsen
@author:     Christian Svindseth
@deffield    updated: Updated
'''


import os
import sys
import cgi
import cgitb
import codecs
import uuid
import yaml
import rdflib
import tempfile
import xlsxwriter
import shutil
import http.cookies as Cookie
import textwrap
import scripts.make_xlsx as mx
from scripts.process_xlsx import Term
import config.fields as fields

__updated__ = '2019-05-03'


#cgitb.enable()
SETUP_DEFAULT = 'darwin'

cookie = Cookie.SimpleCookie(os.environ.get("HTTP_COOKIE"))


method = os.environ.get("REQUEST_METHOD", "GET")

# method = "POST"
#sys.stdout.buffer.write(b"Content-Type: text/html\n\n")

form = cgi.FieldStorage()

# For determining which layout

if 'setup' in form:
    setup = form['setup'].value
else:
    setup = SETUP_DEFAULT
# print(setup)


cores = yaml.load(
    open(os.path.join("config", "config.yaml"), encoding='utf-8'))['cores']

names = []  # For holding a list over the possible setups
for core in cores:
    names.append(core['name'])
    if core['name'] == setup:
        config = core['sheets'][0]


# Put the language in an ordered place
config['languages'] = yaml.load(
    open(os.path.join("config", "config.yaml"), encoding='utf-8'))['languages']

if 'site_language' in cookie:
    site_language = cookie['site_language'].value
else:
    site_language = 'en'


g = rdflib.Graph()
g.load("dwcterms.rdf")
# Populate the terms with the terms from dwc
for s, p, o in g:
    term = Term.get(s)
    if str(p) == "http://www.w3.org/2000/01/rdf-schema#comment":
        term.examples["_"] = str(o)
    elif str(p) == "http://purl.org/dc/terms/description":
        term.definitions["_"] = str(o)

g.load("dcterms.rdf")
# Populate the terms with the terms from dublin core
for s, p, o in g:
    
    term = Term.get(s)
    if str(p) == "http://www.w3.org/2000/01/rdf-schema#comment":
        term.examples["_"] = str(o)
    elif str(p) == "http://purl.org/dc/terms/description":
        term.definitions["_"] = str(o)
    elif str(p) == "http://www.w3.org/2000/01/rdf-schema#label":
        term.labels[o.language] = str(o) 

# Translate terms
t = rdflib.Graph()
t.load("dwctranslations.rdf")
for s, p, o in t:
    if type(o) == rdflib.term.Literal and o.language:
        term = Term.get(s)
        if str(p) == "http://www.w3.org/2004/02/skos/core#example":
            term.examples[o.language] = str(o)
        elif str(p) == "http://www.w3.org/2004/02/skos/core#definition":
            term.definitions[o.language] = str(o)
        elif str(p) == "http://www.w3.org/2004/02/skos/core#prefLabel":
            term.labels[o.language] = str(o)


# Make variable to hold terms not specified in config

# Remove terms in config

dwcnames = []
for term in Term.terms:
    if term.name != '':
        dwcnames.append(term.name)
dwcnames = sorted(dwcnames, key=lambda s: s.lower())
for group in config['grouping']:
    for term in config['terms'][group]:
        if term in dwcnames:
            dwcnames.remove(term) 

# Append these to the config under new headline
fill_name = 'Other'
dwc_name1 = 'Other_DwC_Terms'
dwc_name2 = 'Other_DwC_Terms_cont'
if len(config['grouping']) % 2 != 0:
    config['grouping'].append(fill_name)
    config['terms'][fill_name] = []
config['grouping'].append(dwc_name1)
config['grouping'].append(dwc_name2)
config['terms'][dwc_name1] = []
config['terms'][dwc_name2] = []
ii = 0
for name in dwcnames:
    if ii < len(dwcnames) / 2:
        config['terms'][dwc_name1].append(name)
    else:
        config['terms'][dwc_name2].append(name)
    ii = ii + 1

# print("New config\n", config)
# print("Other_DwC_Terms\n", config['terms'][dwc_name])

# Add terms not in dwc

for field in fields.fields:
    term = Term.get(field['name'])

    if not(term.labels):  # Set the label
        term.labels = {'en': field['disp_name']}

    if not(term.validations):  # Set the validation input

        term.validations = {
            'en': field['valid']['input_message'].replace('\n', '</br>')}


# ignore = []  # ["Organism", "Occurrence", "Taxon"]  # ?

mofterms = [
    "measurementID", "measurementType", "measurementValue",
    "measurementAccuracy", "measurementUnit",
    "measurementDeterminedBy", "measurementDeterminedDate",
    "measurementMethod"
]


from mako.template import Template
from mako.lookup import TemplateLookup

templates = TemplateLookup(
    directories=['templates'], output_encoding='utf-8')


# method = 'POST'


if method == "GET":  # This is for getting the page

    sys.stdout.buffer.write(b"Content-Type: text/html\n\n")
    # Using sys, as print doesn't work for cgi in python3
    fname = os.path.basename(setup)  # Stop any reference to other places
    template = templates.get_template(fname + ".html")

    sys.stdout.flush()
    sys.stdout.buffer.write(
        template.render(config=config, Term=Term, lang=site_language, names=names))

elif method == "POST":
    if 'site_language' in form:
        cookie['site_language'] = form['site_language'].value
        print(cookie.output())
        print("Status: 303 See other")
        print("Location: %s\n" % os.environ["HTTP_REFERER"])
        sys.exit(0)

    reserved = [setup]  # ['measurementorfact', 'uuid']
#     form = ['uuid', 'shipid', 'eventDate',
#             'decimalLatitude', 'decimalLongitude']
    terms = []

    # Build list of terms from config, this is for sorting
    terms_config = []
#     print(config['terms'])
    for group in config['grouping']:
        #         print(group)
        for term in config['terms'][group]:
            terms_config.append(term)

#     print(terms)
#     print(terms_config)
#     print(terms)
    # Use the config terms to sort the terms from the form
    #sys.stdout.buffer.write(b"Content-Type: text/html\n\n")
    #print(form)
    for term in terms_config:
        if term in form and term not in reserved:
            terms.append(term)

    # Add terms from darwin core not in the config

    print("Content-Type: application/vnd.ms-excel")
    if setup == "aen":
        print(
            "Content-Disposition: attachment; filename=AeN_cruisenumber_instr_name.xlsx\n")
    else:
        print(
            "Content-Disposition: attachment; filename=Excel_template.xlsx\n")

    path = "/tmp/" + next(tempfile._get_candidate_names()) + '.xlsx'

    # Need to make the field_dict and append useful info from dwc
    field_dict = mx.make_dict_of_fields()

    for t in Term.terms:
        #         print(field)
        if t.name in field_dict.keys():
            if t.definition(site_language):
                #                 print(t.name)
                valid = field_dict[t.name].validation

                valid['input_message'] = valid['input_message'] + \
                    '\n\nDarwin core supl. info:\n' + \
                    textwrap.fill(
                        ' '.join(t.definition(site_language).split()), width=40)
                field_dict[t.name].set_validation(valid)
        else:
            field_dict[t.name] = mx.Field(
                name=t.name,
                disp_name=t.label(site_language),
                width=len(t.label(site_language)),
                validation={'validate': 'any',
                            'input_title': t.label(site_language),
                            'input_message': 'Darwin core supl. info:\n' +
                            textwrap.fill(
                                ' '.join(t.definition(site_language).split()),
                                width=40)
                            }

            )

#     print(depth.name, depth.disp_name, depth.validation)
#     print(terms)
    metadata = False
    conversions = False
    if 'extrasheet' in config:
        if 'metadata' in config['extrasheet']:
            metadata = True
        if 'conversions' in config['extrasheet']:
            conversions = True

    mx.write_file(path, terms, field_dict, metadata, conversions)

    with open(path, "rb") as f:
        sys.stdout.flush()
        shutil.copyfileobj(f, sys.stdout.buffer)
