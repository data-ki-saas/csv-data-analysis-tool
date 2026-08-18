async def test_get_settings_returns_defaults_when_unset(client):
    response = await client.get("/api/settings")
    assert response.status_code == 200
    assert response.json() == {"theme_mode": "system", "color_theme": "winter"}


async def test_update_settings_persists_and_returns_new_values(client):
    response = await client.put(
        "/api/settings", json={"theme_mode": "dark", "color_theme": "spring"}
    )
    assert response.status_code == 200
    assert response.json() == {"theme_mode": "dark", "color_theme": "spring"}

    follow_up = await client.get("/api/settings")
    assert follow_up.json() == {"theme_mode": "dark", "color_theme": "spring"}


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
    assert response.json() == {"theme_mode": "light", "color_theme": "contrast"}
