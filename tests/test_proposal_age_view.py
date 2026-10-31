"""Default discovery, precise age badges and filter persistence."""
from datetime import datetime, timedelta, timezone
import re

import pytest

from test_admin_interface import ui_client
from test_ux_delivery import db
from app.web.routes import main_routes
from app.services.proposal_page_service import build_proposal_page


def test_age_boundary_and_selected_filter_survive_rendering_and_pagination(db):
    now=datetime(2030,1,31,12,tzinfo=timezone.utc)
    for days in [0,29,30,45]:
        db.execute("INSERT INTO proposals(title,amount,created_by,created_at) VALUES (?,10,1,?)",
                   (f'Age {days}',(now-timedelta(days=days)).replace(tzinfo=None).isoformat()))
    model=build_proposal_page(db,member_id=1,now=now,age='recent',per_page=1)
    assert model['matching_count']==2 and model['total_pages']==2
    assert model['proposal_age']=='recent'
    second=build_proposal_page(db,member_id=1,now=now,age='recent',per_page=1,page=2)
    assert second['proposal_age']=='recent' and second['proposals'][0]['age_days']==29
    old=build_proposal_page(db,member_id=1,now=now,age='old')
    assert old['proposal_age']=='old'
    assert {p['age_days'] for p in old['proposals']}=={30,45}


@pytest.mark.parametrize('language,days_label',[('en','days old'),('es','días')])
def test_default_excludes_old_photos_and_all_restores_exact_overlay(ui_client,language,days_label):
    conn=main_routes.get_db()
    old=(datetime.now(timezone.utc)-timedelta(days=45)).replace(tzinfo=None).isoformat()
    conn.execute("INSERT INTO proposals(title,amount,created_by,created_at,image_filename) VALUES ('Old photo example',10,1,?,'old.png')",(old,))
    conn.commit();conn.close()
    with ui_client.session_transaction() as session:session['lang']=language
    default=ui_client.get('/proposals').get_data(as_text=True)
    assert 'Old photo example' not in default
    assert '<option value="recent" selected>' in default
    all_ages=ui_client.get('/proposals?age=').get_data(as_text=True)
    assert 'Old photo example' in all_ages
    assert re.search(r'class="proposal-age-watermark">45 '+days_label,all_ages)
    assert '<option value="" selected>' in all_ages
    # Legacy bookmarked age views must still work without conflicting defaults.
    old_only=ui_client.get('/proposals?filter=old').get_data(as_text=True)
    assert 'Old photo example' in old_only
    assert '<option value="old" selected>' in old_only
    approved=main_routes.get_db()
    approved.execute("UPDATE proposals SET status='approved' WHERE title='Old photo example'")
    approved.commit();approved.close()
    assert 'class="proposal-age-watermark">45 '+days_label in ui_client.get('/proposals?filter=all&age=').get_data(as_text=True)
