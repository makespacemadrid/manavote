"""Capture populated pages for browser geometry/keyboard regression checks."""
import json
import os
from pathlib import Path
import re

import pytest
from test_admin_interface import ui_client
from app.web.routes import main_routes


@pytest.mark.parametrize('language',['en','es'])
def test_capture_ui_layouts(ui_client, language):
    conn=main_routes.get_db()
    for id, status, multiple in [(1,'open',0),(2,'open',1),(3,'closed',0)]:
        conn.execute('INSERT INTO polls(id,question,options_json,created_by,status,allow_multiple) VALUES (?,?,?,?,?,?)',
            (id,'Which shared workshop should we run next?',json.dumps(['Soldering and electronics','Laser cutting: materials, safety and project planning','Maintaining and calibrating shared 3D printers']),1,status,multiple))
        conn.execute('INSERT INTO poll_votes(poll_id,member_id,option_index) VALUES (?,1,0)',(id,))
    conn.execute("INSERT INTO group_purchases(id,title,description,created_by,cap_at_125) VALUES (1,'Shared electronics order','Choose the parts you need',1,1)")
    conn.execute("INSERT INTO group_purchase_components(id,group_purchase_id,name,unit_price,position) VALUES (1,1,'USB-C connectors',1.5,0)")
    conn.execute("INSERT INTO group_purchase_quantities(component_id,member_id,quantity) VALUES (1,1,2)")
    conn.execute("INSERT INTO group_purchase_shared_costs(group_purchase_id,label,amount) VALUES (1,'Shipping',5)")
    for id,status in [(2,'closed'),(3,'ordered'),(4,'received')]:
        conn.execute('INSERT INTO group_purchases(id,title,created_by,status,cap_at_125) VALUES (?,?,1,?,1)',(id,'Shared order '+status,status))
        conn.execute('INSERT INTO group_purchase_components(id,group_purchase_id,name,unit_price,position) VALUES (?,?,?,2,0)',(id,id,'Development boards'))
        conn.execute('INSERT INTO group_purchase_quantities(component_id,member_id,quantity) VALUES (?,1,2)',(id,))
    conn.execute("INSERT INTO group_purchase_components(id,group_purchase_id,name,unit_price,position) VALUES (5,1,'AA rechargeable batteries',3.75,1)")
    conn.execute("INSERT INTO group_purchase_components(id,group_purchase_id,name,unit_price,position) VALUES (6,1,'ESP32 development boards',6.25,2)")
    conn.execute('INSERT INTO group_purchase_quantities(component_id,member_id,quantity) VALUES (5,2,2)')
    conn.execute("INSERT INTO feedback(id,member_id,source,category,message) VALUES (1,1,'web','suggestion','Make shared purchases easier to find on mobile.')")
    conn.execute("INSERT INTO feedback_notes(feedback_id,author_id,message) VALUES (1,1,'Private note for alignment checks')")
    conn.commit();conn.close()
    output=os.getenv('MANAVOTE_UI_LAYOUT_DIR')
    directory=Path(output) if output else None
    if directory:directory.mkdir(parents=True,exist_ok=True)
    routes={'proposals':'/proposals','proposal':'/proposal/1','new-proposal':'/proposal/new','edit-proposal':'/proposal/1/edit','polls':'/polls','koins':'/koins','groups':'/group-purchases','new-group':'/group-purchases/new','edit-group':'/group-purchases/1/edit','budget':'/budget','settings':'/settings','telegram':'/telegram-settings','about':'/about','password':'/change-password','my-feedback':'/my-feedback','copy-preview':'/admin/copy/proposal/1','qr-labels':'/admin/koins/qr-labels',**{f'admin-{tab}':f'/admin?tab={tab}' for tab in ['members','budget','polls','group_purchases','coins','errors','feedback','settings']}}
    with ui_client.session_transaction() as session:session['lang']=language
    manifest=[]
    for name,path in routes.items():
        response=ui_client.get(path)
        assert response.status_code==200, path
        markup=response.get_data(as_text=True)
        if name=='polls':assert 'class="poll-option"' in markup and '<fieldset class="poll-options" disabled>' in markup
        if directory:
            for image_path in re.findall(r'/koins/qr/[^" ]+\.png',markup):
                image=ui_client.get(image_path);assert image.status_code==200
                image_file=image_path.split('/')[-1];(directory/image_file).write_bytes(image.data)
                markup=markup.replace(image_path,'/qr-assets/'+image_file)
            file=f'{name}-{language}.html';markup=markup.replace('<body>',f'<body data-layout-fixture="{file}">');(directory/file).write_text(markup.replace('/static/','/assets/'))
            manifest.append({'name':name,'lang':language,'file':file})
    if directory:
        (directory/f'manifest-{language}.json').write_text(json.dumps(manifest))
