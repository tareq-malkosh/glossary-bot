from flask import abort, current_app, request
from . import gloss as app
from . import db
from .models import Definition, Interaction
from sqlalchemy import func, distinct, sql
from requests import post
from datetime import datetime
import json
import random
import re

STATS_CMDS = ("stats",)
RECENT_CMDS = ("learnings", "recent")
HELP_CMDS = ("help", "?")
SET_CMDS = ("=",)
DELETE_CMDS = ("delete",)
SEARCH_CMDS = ("search",)

ALIAS_KEYWORDS = ("see also", "see")

BOT_NAME = "SpotHero Glossary"
BOT_EMOJI = ":spotherocar:"

'''
values posted by Slack:
    token: the authenticaton token from Slack; available in the integration settings.
    team_domain: the name of the team (i.e. what shows up in the URL: {xxx}.slack.com)
    team_id: unique ID for the team
    channel_name: the name of the channel the message was sent from
    channel_id: unique ID for the channel the message was sent from
    user_name: the name of the user that sent the message
    user_id: unique ID for the user that sent the message
    command: the command that was used to generate the request (like '/gloss')
    text: the text that was sent along with the command (like everything after '/gloss ')
'''

def get_payload_values(channel_id="", text=None):
    ''' Get a dict describing a standard webhook
    '''
    payload_values = {}
    payload_values['channel'] = channel_id
    payload_values['text'] = text
    payload_values['username'] = BOT_NAME
    payload_values['icon_emoji'] = BOT_EMOJI
    return payload_values

def send_webhook_with_attachment(channel_id="", text=None, fallback="", pretext="", title="", color="#f33373", image_url=None, mrkdwn_in=[]):
    ''' Send a webhook with an attachment, for a more richly-formatted message.
        see https://api.slack.com/docs/attachments
    '''
    # don't send empty messages
    if not text:
        return

    # get the standard payload dict
    # :NOTE: sending text defined as 'pretext' to the standard payload and leaving
    #        'pretext' in the attachment empty so that I can use markdown styling.
    payload_values = get_payload_values(channel_id=channel_id, text=pretext)
    # build the attachment dict
    attachment_values = {}
    attachment_values['fallback'] = fallback
    attachment_values['pretext'] = None
    attachment_values['title'] = title
    attachment_values['text'] = text
    attachment_values['color'] = color
    attachment_values['image_url'] = image_url
    if len(mrkdwn_in):
        attachment_values['mrkdwn_in'] = mrkdwn_in
    # add the attachment dict to the payload and jsonify it
    payload_values['attachments'] = [attachment_values]
    payload = json.dumps(payload_values)

    # return the response
    return post(current_app.config['SLACK_WEBHOOK_URL'], data=payload)

def get_image_url(text):
    ''' Extract an image url from the passed text. If there are multiple image urls,
        only the first one will be returned.
    '''
    if 'http' not in text:
        return None

    for chunk in text.split(' '):
        if verify_image_url(text) and verify_url(text):
            return chunk

    return None

def make_bold(text):
    ''' make the passed text bold, accounting for newlines
    '''
    newline_split = text.split("\n")
    bold_split = []
    for line in newline_split:
        bold_line = line
        if line.strip() != "":
            bold_line = "*{}*".format(line.strip())
        bold_split.append(bold_line)

    return "\n".join(bold_split)

def verify_url(text):
    ''' verify that the passed text is a URL

        Adapted from @adamrofer's Python port of @dperini's pattern here: https://gist.github.com/dperini/729294
    '''
    url_pattern = re.compile("^(?:(?:https?)://|)(?:(?!(?:10|127)(?:\.\d{1,3}){3})(?!(?:169\.254|192\.168)(?:\.\d{1,3}){2})(?!172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})(?:[1-9]\d?|1\d\d|2[01]\d|22[0-3])(?:\.(?:1?\d{1,2}|2[0-4]\d|25[0-5])){2}(?:\.(?:[1-9]\d?|1\d\d|2[0-4]\d|25[0-4]))|(?:(?:[a-z\u00a1-\uffff0-9]-*)*[a-z\u00a1-\uffff0-9]+)(?:\.(?:[a-z\u00a1-\uffff0-9]-*)*[a-z\u00a1-\uffff0-9]+)*(?:\.(?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)))(?::\d{2,5})?(?:/\S*)?$", re.UNICODE)
    return url_pattern.match(text)

def verify_image_url(text):
    ''' Verify that the passed text is an image URL.

        We're verifying image URLs for inclusion in Slack's Incoming Webhook integration, which
        requires a scheme at the beginning (http(s)) and a file extention at the end to render
        correctly. So, a URL which passes verify_url() (like example.com/kitten.gif) might not
        pass this test. If you need to test that the URL is both valid AND an image suitable for
        the Incoming Webhook integration, run it through both verify_url() and verify_image_url().
    '''
    return (re.match('http', text) and re.search(r'[gif|jpg|jpeg|png|bmp]$', text))

def get_stats():
    ''' Gather and return some statistics
    '''
    entries = db.session.query(func.count(Definition.term)).scalar()
    definers = db.session.query(func.count(distinct(Definition.user_name))).scalar()
    queries = db.session.query(func.count(Interaction.action)).scalar()
    outputs = (
        ("I have definitions for", entries, "term", "terms", "I don't have any definitions"),
        ("", definers, "person has defined terms", "people have defined terms", "Nobody has defined terms"),
        ("I've been asked for definitions", queries, "time", "times", "Nobody has asked me for definitions")
    )
    lines = []
    for prefix, period, singular, plural, empty_line in outputs:
        if period:
            lines.append("{}{} {}".format("{} ".format(prefix) if prefix else "", period, singular if period == 1 else plural))
        else:
            lines.append(empty_line)
    # return the message
    return "\n".join(lines)

def get_learnings(how_many=12, sort_order="recent", offset=0):
    ''' Gather and return some recent definitions
    '''
    order_descending = Definition.creation_date.desc()
    order_random = func.random()
    order_alphabetical = Definition.term
    order_function = order_descending
    prefix_singluar = "I recently learned the definition for"
    prefix_plural = "I recently learned definitions for"
    no_definitions_text = "I haven't learned any definitions yet."
    if sort_order == "random":
        order_function = order_random
    elif sort_order == "alpha":
        order_function = order_alphabetical

    if sort_order == "random" or sort_order == "alpha" or offset > 0:
        prefix_singluar = "I know the definition for"
        prefix_plural = "I know definitions for"

    # if how_many is 0, ignore offset and return all results
    if how_many == 0:
        definitions = db.session.query(Definition).order_by(order_function).all()
    # if order is random and there is an offset, randomize the results after the query
    elif sort_order == "random" and offset > 0:
        definitions = db.session.query(Definition).order_by(order_descending).limit(how_many).offset(offset).all()
        random.shuffle(definitions)
    else:
        definitions = db.session.query(Definition).order_by(order_function).limit(how_many).offset(offset).all()

    if not definitions:
        return no_definitions_text, no_definitions_text

    wording = prefix_plural if len(definitions) > 1 else prefix_singluar
    plain_text = "{}: {}".format(wording, ', '.join([item.term for item in definitions]))
    rich_text = "{}: {}".format(wording, ', '.join([make_bold(item.term) for item in definitions]))
    return plain_text, rich_text

def parse_learnings_params(command_params):
    ''' Parse the passed learnings command params
    '''
    recent_args = {}
    # extract parameters
    params_list = command_params.split(' ')
    for param in params_list:
        if param == "random":
            recent_args['sort_order'] = param
            continue
        if param == "alpha" or param == "alphabetical":
            recent_args['sort_order'] = "alpha"
            continue
        if param == "all":
            recent_args['how_many'] = 0
            continue
        try:
            passed_int = int(param)
            if 'how_many' not in recent_args:
                recent_args['how_many'] = passed_int
            elif 'offset' not in recent_args:
                recent_args['offset'] = passed_int
        except ValueError:
            continue

    return recent_args

def log_query(term, user_name, action):
    ''' Log a query into the interactions table
    '''
    try:
        db.session.add(Interaction(term=term, user_name=user_name, action=action))
        db.session.commit()
    except:
        pass

def query_definition(term):
    ''' Query the definition for a term from the database
    '''
    return Definition.query.filter(func.lower(Definition.term) == func.lower(term)).first()

def get_matches_for_term(term):
    ''' Search the glossary for entries that are matches for the passed term.
    '''
    # strip pattern-matching metacharacters from the term
    stripped_term = re.sub(r'\||_|%|\*|\+|\?|\{|\}|\(|\)|\[|\]', '', term)
    # get ILIKE matches for the term
    # in SQL: SELECT term FROM definitions WHERE term ILIKE '%{}%'.format(stripped_term);
    like_matches = Definition.query.filter(Definition.term.ilike("%{}%".format(stripped_term)))
    like_terms = [entry.term for entry in like_matches]

    # get TSV matches for the term
    tsv_matches = db.session.query('term').from_statement(sql.text(
        '''SELECT * FROM definitions WHERE tsv_search @@ plainto_tsquery(:term) ORDER BY ts_rank(tsv_search, plainto_tsquery(:term)) DESC;'''
    )).params(term=stripped_term)
    tsv_terms = [entry[0] for entry in tsv_matches]

    # put ilike matches that aren't in the TSV list at the front
    match_terms = list(tsv_terms)
    for check_term in like_terms:
        if check_term not in tsv_terms:
            match_terms.insert(0, check_term)

    return match_terms

def get_command_action_and_params(command_text):
    ''' Parse the passed string for a command action and parameters
    '''
    command_components = command_text.split(' ')
    command_action = command_components[0].lower()
    command_params = " ".join(command_components[1:])
    return command_action, command_params

def check_definition_for_alias(definition):
    ''' If the passed definition starts with a keyword in ALIAS_KEYWORDS, strip
        that prefix from the definition and return it.
    '''
    for keyword in ALIAS_KEYWORDS:
        if definition.lower().startswith(keyword):
            return re.split(keyword, definition, flags=re.IGNORECASE)[1].strip()

    return None

def query_definition_and_get_response(slash_command, command_text, user_name, channel_id, private_response):
    ''' Get the definition for the passed term and return the appropriate responses
    '''
    # query the definition
    entry = query_definition(command_text)
    if not entry:
        # remember this query
        log_query(term=command_text, user_name=user_name, action="not_found")

        message = "Sorry, but *{bot_name}* has no definition for *{term}*. You can set a definition with the command *{command} {term} = _definition_*".format(bot_name=BOT_NAME, command=slash_command, term=command_text)

        search_results = get_matches_for_term(command_text)
        if len(search_results):
            search_results_styled = ', '.join([make_bold(term) for term in search_results])
            message = "{}, or try asking for one of these terms that may be related: {}".format(message, search_results_styled)

        return message, 200

    # remember this query
    log_query(term=command_text, user_name=user_name, action="found")

    # if the definition starts with an alias keyphrase, check to see if the rest
    # of the definition matches another entry, and return that definition instead
    alias_term = check_definition_for_alias(entry.definition)
    if alias_term:
        alias_entry = query_definition(alias_term)

        if alias_entry:
            entry = alias_entry

    fallback = "{name} {command} {term}: {definition}".format(name=user_name, command=slash_command, term=entry.term, definition=entry.definition)
    if not private_response:
        image_url = get_image_url(entry.definition)
        pretext = "*{name}* {command} {text}".format(name=user_name, command=slash_command, text=command_text)
        title = entry.term
        text = entry.definition
        send_webhook_with_attachment(channel_id=channel_id, text=text, fallback=fallback, pretext=pretext, title=title, image_url=image_url)
        return "", 200
    else:
        return fallback, 200

def search_term_and_get_response(command_text):
    ''' Search the database for the passed term and return the results
    '''
    # query the definition
    search_results = get_matches_for_term(command_text)
    if len(search_results):
        search_results_styled = ', '.join([make_bold(term) for term in search_results])
        message = "{bot_name} found {term} in: {results}".format(bot_name=BOT_NAME, term=make_bold(command_text), results=search_results_styled)
    else:
        message = "{bot_name} could not find {term} in any terms or definitions.".format(bot_name=BOT_NAME, term=make_bold(command_text))

    return message, 200

def set_definition_and_get_response(slash_command, command_params, user_name):
    ''' Set the definition for the passed parameters and return the approriate responses
    '''
    set_components = command_params.split('=', 1)
    set_term = set_components[0].strip()
    set_value = set_components[1].strip() if len(set_components) > 1 else ""

    # reject poorly formed set commands
    if "=" not in command_params or not set_term or not set_value:
        return "Sorry, but *{bot_name}* didn't understand your command. You can set definitions like this: *{command} EW = Eligibility Worker*".format(bot_name=BOT_NAME, command=slash_command), 200

    # reject attempts to set reserved terms
    if set_term.lower() in STATS_CMDS + RECENT_CMDS + HELP_CMDS:
        return "Sorry, but *{bot_name}* can't set a definition for {term} because it's a reserved term.".format(bot_name=BOT_NAME, term=make_bold(set_term))

    # check the database to see if the term's already defined
    entry = query_definition(set_term)
    if entry:
        if set_term != entry.term or set_value != entry.definition:
            # update the definition in the database
            last_term = entry.term
            last_value = entry.definition
            entry.term = set_term
            entry.definition = set_value
            entry.user_name = user_name
            entry.creation_date = datetime.utcnow()
            try:
                db.session.add(entry)
                db.session.commit()
            except Exception as e:
                return "Sorry, but *{bot_name}* was unable to update that definition: {message}, {args}".format(bot_name=BOT_NAME, message=e.message, args=e.args), 200

            return "*{bot_name}* has set the definition for {term} to {definition}, overwriting the previous entry, which was {prev_term} defined as {prev_def}".format(bot_name=BOT_NAME, term=make_bold(set_term), definition=make_bold(set_value), prev_term=make_bold(last_term), prev_def=make_bold(last_value)), 200

        else:
            return "*{bot_name}* already knows that the definition for {term} is {definition}".format(bot_name=BOT_NAME, term=make_bold(set_term), definition=make_bold(set_value)), 200

    # save the definition in the database
    entry = Definition(term=set_term, definition=set_value, user_name=user_name)
    try:
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        return "Sorry, but *{bot_name}* was unable to save that definition: {message}, {args}".format(bot_name=BOT_NAME, message=e.message, args=e.args), 200

    return "*{bot_name}* has set the definition for {term} to {definition}".format(bot_name=BOT_NAME, term=make_bold(set_term), definition=make_bold(set_value)), 200

#
# ROUTES
#

@app.route('/', methods=['POST'])
def index():
    # verify that the request is authorized
    if request.form['token'] != current_app.config['SLACK_TOKEN']:
        abort(401)

    # get the user name and channel ID
    user_name = request.form['user_name']
    channel_id = request.form['channel_id']

    # get the slash command
    slash_command = request.form['command']

    # strip excess spaces from the text
    full_text = request.form['text'].strip()
    full_text = re.sub(" +", " ", full_text)
    command_text = full_text

    #
    # GET definition (for a single word that can't be interpreted as a command)
    #

    # if the text is a single word that's not a single-word command, treat it as a get
    if command_text.count(" ") is 0 and len(command_text) > 0 and \
       command_text.lower() not in STATS_CMDS + RECENT_CMDS + HELP_CMDS + SET_CMDS:
        return query_definition_and_get_response(slash_command, command_text, user_name, channel_id, False)

    #
    # SET definition
    #

    # if the text contains an '=', treat it as a 'set' command
    if '=' in command_text:
        return set_definition_and_get_response(slash_command, command_text, user_name)

    # we'll respond privately if the text is prefixed with 'shh ' (or any number of s followed by any number of h)
    shh_pattern = re.compile(r'^s+h+ ')
    private_response = shh_pattern.match(command_text)
    if private_response:
        # strip the 'shh' from the command text
        command_text = shh_pattern.sub('', command_text)

    # extract the command action and parameters
    command_action, command_params = get_command_action_and_params(command_text)

    #
    # DELETE definition
    #

    if command_action in DELETE_CMDS:
        delete_term = command_params

        # verify that the definition is in the database
        entry = query_definition(delete_term)
        if not entry:
            return "Sorry, but *{bot_name}* has no definition for {term}".format(bot_name=BOT_NAME, term=make_bold(delete_term)), 200

        # delete the definition from the database
        try:
            db.session.delete(entry)
            db.session.commit()
        except Exception as e:
            return "Sorry, but *{bot_name}* was unable to delete that definition: {message}, {args}".format(bot_name=BOT_NAME, message=e.message, args=e.args), 200

        return "*{bot_name}* has deleted the definition for {term}, which was {definition}".format(bot_name=BOT_NAME, term=make_bold(delete_term), definition=make_bold(entry.definition)), 200

    #
    # SEARCH for a string
    #

    if command_action in SEARCH_CMDS:
        search_term = command_params

        return search_term_and_get_response(search_term)

    #
    # HELP
    #

    if command_action in HELP_CMDS or command_text.strip() == "":
        return "*{command} _term_* to show the definition for a term\n*{command} _term_ = _definition_* to set the definition for a term\n*{command} _alias_ = see _term_* to set an alias for a term\n*{command} delete _term_* to delete the definition for a term\n*{command} stats* to show usage statistics\n*{command} recent* to show recently defined terms\n*{command} search _term_* to search terms and definitions\n*{command} shh _command_* to get a private response\n*{command} help* to see this message\n<https://github.com/codeforamerica/glossary-bot/issues|report bugs and request features>".format(command=slash_command), 200

    #
    # STATS
    #

    if command_action in STATS_CMDS:
        stats_newline = get_stats()
        stats_comma = re.sub("\n", ", ", stats_newline)
        if not private_response:
            # send the message
            fallback = "{name} {command} stats: {comma}".format(name=user_name, command=slash_command, comma=stats_comma)
            pretext = "*{name}* {command} stats".format(name=user_name, command=slash_command)
            title = ""
            send_webhook_with_attachment(channel_id=channel_id, text=stats_newline, fallback=fallback, pretext=pretext, title=title)
            return "", 200

        else:
            return stats_comma, 200

    #
    # LEARNINGS/RECENT
    #

    if command_action in RECENT_CMDS:
        # extract parameters
        recent_args = parse_learnings_params(command_params)
        learnings_plain_text, learnings_rich_text = get_learnings(**recent_args)
        if not private_response:
            # send the message
            fallback = "{name} {command} {action} {params}: {text}".format(name=user_name, command=slash_command, action=command_action, params=command_params, text=learnings_plain_text)
            pretext = "*{name}* {command} {action} {params}".format(name=user_name, command=slash_command, action=command_action, params=command_params)
            title = ""
            send_webhook_with_attachment(channel_id=channel_id, text=learnings_rich_text, fallback=fallback, pretext=pretext, title=title, mrkdwn_in=["text"])
            return "", 200

        else:
            return learnings_plain_text, 200

    #
    # GET definition (for any text that wasn't caught before this)
    #

    # check the definition
    return query_definition_and_get_response(slash_command, command_text, user_name, channel_id, private_response)
