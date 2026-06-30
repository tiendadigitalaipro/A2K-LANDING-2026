"""A2K Webhook Server v3 — standalone con whatsapp_send"""

import os, sys, json, hmac, hashlib, logging
from datetime import datetime
from flask import Flask, request, jsonify
import requests

# ─── CONFIG ───
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "http://localhost:3099/send-text")
LOG_FILE = os.getenv("LOG_FILE", os.path.join(os.getcwd(), "a2k_log.json"))

# ─── LOG ───
def log_event(etype, data, status="ok"):
    entry = {"timestamp": datetime.now().isoformat(), "event": etype, "status": status, "data": data}
    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE) as f:
            try: logs = json.load(f)
            except: pass
    logs.append(entry)
    if len(logs) > 500: logs = logs[-500:]
    with open(LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2)

# ─── WHATSAPP ───
def send_whatsapp(phone, message):
    phone = phone.replace("+", "").strip()
    try:
        r = requests.post(WHATSAPP_API_URL, json={"phone": phone, "message": message, "isGroup": False}, timeout=8)
        with open(os.path.expanduser("~/Desktop/wa_debug.log"), "a") as f:
            f.write(f"[WA] {r.status_code} {r.text}\n")
        return r.status_code == 200
    except Exception as e:
        with open(os.path.expanduser("~/Desktop/wa_debug.log"), "a") as f:
            f.write(f"[WA ERROR] {e}\n")
        return False

# ─── DEEPSEEK FAQ ───
def classify_faq(msg):
    prompt = "Clasifica esta pregunta para e-commerce. Responde SOLO: STOCK | PRECIO | ENVIO | PAGO | GARANTIA | HORARIO | OTRO\n\n" + msg[:300]
    try:
        r = requests.post(DEEPSEEK_API_URL,
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.1, "max_tokens": 10}, timeout=8)
        if r.status_code == 200:
            c = r.json()["choices"][0]["message"]["content"].strip()
            return c if c in ("STOCK","PRECIO","ENVIO","PAGO","GARANTIA","HORARIO","OTRO") else "OTRO"
    except:
        pass
    return "OTRO"

def faq_response(cat, prod=None):
    p = prod or "este producto"
    rs = {
        "STOCK": f"🔍 ¡Sí! **{p}** está disponible. ¿Quieres que te ayude con el pedido? 📦",
        "PRECIO": f"💰 El precio de **{p}** está en nuestra tienda online. ¿Te paso el enlace?",
        "ENVIO": "🚚 **Envíos:** Ocumare 24-48h · Venezuela 2-5 días · Desde $3 · GRATIS >$50",
        "PAGO": "💳 **Pagos:** Transferencia · Pago Móvil · PayPal · PagueloFacil · Efectivo",
        "GARANTIA": "🛡️ **Garantía:** 30 días · Cambio por defecto · Soporte WhatsApp",
        "HORARIO": "⏰ **Horarios:** Lun-Vie 9AM-6PM · Sáb 9AM-1PM · Tienda online 24/7",
        "OTRO": "😊 ¡Gracias! Un asesor te responderá pronto."
    }
    return rs.get(cat, rs["OTRO"])

# ─── NOTIFICACIONES ───
def confirmar_compra(phone, nombre, pedido, items, total):
    return send_whatsapp(phone,
        f"✅ *¡Gracias por tu compra, {nombre}!* 🎉\n📌 #{pedido}\n📦 {items}\n💰 ${total:.2f}\n⏳ Te enviaremos la guía en 24-48h.\n💬 ¿Dudas? Responde aquí.\n🚀 *A2K Digital Studio*")

def enviar_guia(phone, pedido, guia, courier="MRW"):
    url_t = {"MRW": f"https://www.mrw.com.ve/tracking/{guia}", "ZOOM": f"https://zoom.com.ve/rastreo/{guia}"}.get(courier.upper(), f"https://www.{courier}.com/tracking/{guia}")
    return send_whatsapp(phone,
        f"📦 *¡Tu pedido ya viaja!* 🚚\n📌 #{pedido}\n🔖 Guía: {guia}\n🔗 {url_t}\n💬 ¿Dudas? Escríbenos.\n⚡ *A2K Digital Studio*")

def pedir_resena(phone, nombre, producto):
    return send_whatsapp(phone,
        f"⭐ *¿Cómo fue tu experiencia, {nombre}?*\nRecibiste *{producto}* ✅\nCalifícanos ⭐\n🎁 *BONO:* Usa *A2K10* para 10% OFF 🎉")

def recuperar_carrito(phone, nombre, producto, enlace):
    return send_whatsapp(phone,
        f"👋 *¡Hola {nombre}!*\nVimos que dejaste *{producto}* en tu carrito 🤔\n🔥 *10% OFF* con *A2K10* 🎉\n👉 {enlace}\n¿Te ayudamos? 😊")

# ─── WEBHOOK HANDLER ───
def handle(data):
    event = data.get("event", "unknown")
    print(f"\n⚡ EVENTO: {event}")
    log_event("in", {"event": event}, "processing")

    if event == "new_product":
        p = data.get("product", data)
        log_event("new_product", p)
        return {"status": "ok", "message": f"Producto: {p.get('nombre', '?')}"}

    elif event == "chat_message":
        msg = data.get("message", "")
        prod = data.get("product_name")
        cat = classify_faq(msg)
        resp = faq_response(cat, prod)
        log_event("faq", {"cat": cat, "msg": msg[:80]})
        return {"status": "ok", "category": cat, "response": resp}

    elif event == "whatsapp_send":
        phone = data.get("to", "").replace("+", "")
        msg = data.get("message", "")
        print(f"  📱 Enviando WhatsApp a {phone}")
        ok = send_whatsapp(phone, msg)
        log_event("whatsapp", {"to": phone, "ok": ok})
        return {"status": "ok" if ok else "error", "action": "enviado", "to": phone}

    elif event == "order_confirmed":
        o = data.get("order", data)
        confirmar_compra(o.get("phone"), o.get("customer_name", o.get("nombre")),
                        o.get("id", o.get("pedido")), o.get("items"), float(o.get("total", 0)))
        log_event("order_confirmed", o)
        return {"status": "ok", "action": "confirmacion"}

    elif event == "order_shipped":
        o = data.get("order", data)
        enviar_guia(o.get("phone"), o.get("id"), o.get("tracking_code"), o.get("courier"))
        log_event("shipped", o)
        return {"status": "ok", "action": "guia_enviada"}

    elif event == "order_delivered":
        o = data.get("order", data)
        pedir_resena(o.get("phone"), o.get("customer_name"), o.get("product_name"))
        log_event("review", o)
        return {"status": "ok", "action": "resena"}

    elif event == "cart_abandoned":
        c = data.get("cart", data)
        recuperar_carrito(c.get("phone"), c.get("customer_name", "Cliente"),
                         c.get("product_name"), c.get("cart_url", ""))
        log_event("cart", c)
        return {"status": "ok", "action": "recordatorio"}

    log_event("unknown", data, "warning")
    return {"status": "warning", "message": f"Evento no reconocido: {event}"}

# ─── FLASK ───
app = Flask(__name__)

# CORS headers para que el chat funcione desde Vercel
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Origin"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    return response

@app.route("/webhook/a2k", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}
    return jsonify(handle(data))

@app.route("/health")
def health():
    return jsonify({"status": "ok", "server": "A2K v3", "deepseek": bool(DEEPSEEK_API_KEY)})

@app.route("/log")
def log():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE) as f:
            return jsonify(json.load(f)[-20:])
    return jsonify([])

if __name__ == "__main__":
    PORT = 5001
    print(f"\n🚀 A2K Webhook Server v3 → http://0.0.0.0:{PORT}")
    print(f"   Eventos: new_product | chat_message | whatsapp_send | order_* | cart_abandoned")
    app.run(host="0.0.0.0", port=PORT, debug=False)
