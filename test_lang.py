# Test to see what session is during the set_language request

from app import app

c = app.test_client()

# 1. Start with EN
c.get("/login")
c.get("/set-language/en", headers={"Referer": "/login"})
c.post(
    "/login",
    data={"username": "manadmin", "password": "carpediem42"},
    follow_redirects=True,
)

# 2. Get dashboard - should show EN
r = c.get("/dashboard")
print("EN - Panel:", "Panel" in r.data.decode())
print("EN - Dashboard:", "Dashboard" in r.data.decode())

# 3. Switch to ES
c.get("/set-language/es", headers={"Referer": "/dashboard"})

# 4. Get dashboard - should show ES
r = c.get("/dashboard")
print("ES - Panel:", "Panel" in r.data.decode())
print("ES - Dashboard:", "Dashboard" in r.data.decode())
