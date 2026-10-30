"""Poll choices retain clear saved state and closed controls across locales."""
from flask import render_template, session
import pytest
from app import app

@pytest.mark.parametrize('language,saved,choice',[('en','Saved vote','Choose one option'),('es','Voto guardado','Elige una opción')])
@pytest.mark.parametrize('status',['open','closed'])
def test_poll_choice_group_and_saved_state(language,saved,choice,status):
    poll=dict(id=7,question='Which workshop?',status=status,allow_multiple=False,
        creator='Ada',created_at='2026-10-30',options=['Soldering','Laser cutting'],
        counts=[1,0],total_voters=1,user_votes=[0],votes=[])
    with app.test_request_context('/polls'):
        session.update(member_id=1,username='Ada',lang=language)
        html=render_template('polls.html',polls=[poll],session_lang=language,
            is_web_vote_enabled=True,is_telegram_linked=True)
    assert f'<legend>{choice}</legend>' in html
    assert saved in html and 'class="poll-option"' in html
    assert ('<fieldset class="poll-options" disabled>' in html)==(status=='closed')
    assert 'aria-labelledby="poll-title-7"' in html
    assert html.index('class="web-vote-form"') < html.index('class="poll-result"')


def test_multiple_choice_explains_additive_behavior_and_clear_action():
    poll=dict(id=8,question='Choose topics',status='open',allow_multiple=True,
        creator='Ada',created_at='2026-10-30',options=['One','Two'],
        counts=[1,0],total_voters=1,user_votes=[0],votes=[])
    with app.test_request_context('/polls'):
        session.update(member_id=1,lang='en')
        html=render_template('polls.html',polls=[poll],session_lang='en',
            is_web_vote_enabled=True,is_telegram_linked=True)
    assert 'Voting adds selected options.' in html
    assert 'name="clear_vote" value="1"' in html
    assert 'type="checkbox"' in html
