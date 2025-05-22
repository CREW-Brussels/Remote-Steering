module("luci.controller.wifidata", package.seeall)

function index()
    -- Register a menu entry under "Network" called "WiFi Data"
    entry({"admin", "network", "wifidata"}, template("wifidata/index"), _("WiFi Data"), 90)
    -- Register a JSON endpoint to serve the WiFi data
    entry({"admin", "network", "wifidata", "json"}, call("action_wifidata_json"), nil)
end

function action_wifidata_json()
    local http  = require "luci.http"
    local jsonc = require "luci.jsonc"
    local data = {}

    local f = io.open("/tmp/wifidata.json", "r")
    if f then
        local content = f:read("*a")
        f:close()
        data = jsonc.parse(content) or {}
    end

    http.prepare_content("application/json")
    http.write_json(data)
end
