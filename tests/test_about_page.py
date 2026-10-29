import html
import re

import pytest

from app import app
from app.web.routes.helpers.main_helpers import link_word
from translations import TRANSLATIONS


@pytest.mark.parametrize('language,budget,proposals', [('en','Budget','Proposals'),('es','presupuesto','propuestas')])
def test_about_links_original_sentence_words_in_each_language(language, budget, proposals):
    client=app.test_client()
    with client.session_transaction() as session:
        session.update(lang=language,member_id=1,username='member')
    response=client.get('/about')
    assert response.status_code == 200
    markup=response.get_data(as_text=True)
    for heading,word,href,key in [('about-funding',budget,'/budget','About funding 1'),('about-tracking',proposals,'/proposals','About tracking 1')]:
        section=re.search(r'<section[^>]*aria-labelledby="'+heading+r'">(.*?)</section>',markup,re.S).group(1)
        assert f'<a href="{href}">{word}</a>' in section
        plain=html.unescape(re.sub(r'<[^>]+>','',section))
        assert TRANSLATIONS[language][key] in plain
    assert 'class="about-inline-link"' in markup
    assert 'class="about-extras"' in markup
    assert 'class="btn btn-secondary" type="button" data-feedback-open' not in markup


def test_inline_word_linking_escapes_content_and_rejects_script_urls():
    linked=str(link_word('Budget <script>bad</script>', 'Budget', '/budget'))
    assert linked == '<a href="/budget">Budget</a> &lt;script&gt;bad&lt;/script&gt;'
    assert '<a' not in str(link_word('Budget', 'Budget', 'javascript:alert(1)'))
