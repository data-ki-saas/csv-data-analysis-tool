async def test_get_settings_returns_defaults_when_unset(client):
    response = await client.get("/api/settings")
    assert response.status_code == 200
    assert response.json() == {
        "theme_mode": "system",
        "color_theme": "winter",
        "header_presets": [],
        "footer_presets": [],
    }


async def test_update_settings_persists_and_returns_new_values(client):
    response = await client.put(
        "/api/settings", json={"theme_mode": "dark", "color_theme": "spring"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["theme_mode"] == "dark"
    assert body["color_theme"] == "spring"

    follow_up = await client.get("/api/settings")
    assert follow_up.json()["theme_mode"] == "dark"
    assert follow_up.json()["color_theme"] == "spring"


async def test_update_settings_rejects_unknown_color_theme(client):
    response = await client.put(
        "/api/settings", json={"theme_mode": "dark", "color_theme": "neon"}
    )
    assert response.status_code == 422


async def test_update_settings_overwrites_previous_value(client):
    await client.put("/api/settings", json={"theme_mode": "dark", "color_theme": "spring"})
    response = await client.put(
        "/api/settings", json={"theme_mode": "light", "color_theme": "contrast"}
    )
    body = response.json()
    assert body["theme_mode"] == "light"
    assert body["color_theme"] == "contrast"


_HEADER_PRESET = {"id": "h1", "title": "Acme Corp", "logo": None, "enabled": True}
_FOOTER_PRESET = {"id": "f1", "html": "<p>123 Main St</p>", "enabled": True}


async def test_update_header_presets_round_trips(client):
    response = await client.put("/api/settings/header-presets", json={"presets": [_HEADER_PRESET]})
    assert response.status_code == 200
    assert response.json()["header_presets"] == [_HEADER_PRESET]

    follow_up = await client.get("/api/settings")
    assert follow_up.json()["header_presets"] == [_HEADER_PRESET]


async def test_update_footer_presets_round_trips(client):
    response = await client.put("/api/settings/footer-presets", json={"presets": [_FOOTER_PRESET]})
    assert response.status_code == 200
    assert response.json()["footer_presets"] == [_FOOTER_PRESET]


async def test_updating_header_presets_does_not_clobber_theme_or_footer_presets(client):
    await client.put("/api/settings", json={"theme_mode": "dark", "color_theme": "spring"})
    await client.put("/api/settings/footer-presets", json={"presets": [_FOOTER_PRESET]})

    response = await client.put("/api/settings/header-presets", json={"presets": [_HEADER_PRESET]})
    body = response.json()
    assert body["theme_mode"] == "dark"
    assert body["color_theme"] == "spring"
    assert body["footer_presets"] == [_FOOTER_PRESET]
    assert body["header_presets"] == [_HEADER_PRESET]


async def test_header_presets_rejects_more_than_five(client):
    presets = [{**_HEADER_PRESET, "id": str(i), "enabled": False} for i in range(6)]
    response = await client.put("/api/settings/header-presets", json={"presets": presets})
    assert response.status_code == 422


async def test_header_presets_rejects_more_than_one_enabled(client):
    presets = [
        {**_HEADER_PRESET, "id": "h1", "enabled": True},
        {**_HEADER_PRESET, "id": "h2", "enabled": True},
    ]
    response = await client.put("/api/settings/header-presets", json={"presets": presets})
    assert response.status_code == 400


async def test_header_presets_rejects_oversized_logo(client):
    # Comfortably over the 200KB default (max_logo_size_kb) once base64-decoded.
    oversized_logo = "data:image/png;base64," + ("A" * 300_000)
    response = await client.put(
        "/api/settings/header-presets",
        json={"presets": [{**_HEADER_PRESET, "logo": oversized_logo}]},
    )
    assert response.status_code == 400
    assert "KB limit" in response.json()["detail"]


async def test_footer_presets_strips_disallowed_html(client):
    dirty = {"id": "f1", "html": "<p>Hi</p><script>alert('xss')</script>", "enabled": False}
    response = await client.put("/api/settings/footer-presets", json={"presets": [dirty]})
    assert response.status_code == 200
    saved_html = response.json()["footer_presets"][0]["html"]
    assert "<script>" not in saved_html
    assert "<p>Hi</p>" in saved_html


async def test_footer_presets_rejects_more_than_one_enabled(client):
    presets = [
        {**_FOOTER_PRESET, "id": "f1", "enabled": True},
        {**_FOOTER_PRESET, "id": "f2", "enabled": True},
    ]
    response = await client.put("/api/settings/footer-presets", json={"presets": presets})
    assert response.status_code == 400
