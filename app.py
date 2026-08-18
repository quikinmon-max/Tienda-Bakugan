import streamlit as st
import pymongo
import base64
import uuid
import urllib.parse
from datetime import datetime, timedelta
from PIL import Image, ImageOps, ImageFile, ImageDraw, ImageFont
import io
from bson.objectid import ObjectId
from collections import defaultdict 

# --- BLINDAJE PARA FOTOS PESADAS ---
ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None

# ---------------- CONFIGURACIÓN DE PÁGINA ----------------
st.set_page_config(page_title="Bakugan Market", page_icon="🔥", layout="wide")

def hora_qro():
    return datetime.utcnow() - timedelta(hours=6)

# ---------------- INICIALIZAR MEMORIA ----------------
if 'limite_items' not in st.session_state:
    st.session_state.limite_items = 12

if 'admin_autenticado' not in st.session_state:
    st.session_state.admin_autenticado = False

if 'welcome_shown' not in st.session_state:
    st.session_state.welcome_shown = False

# --- CANDADO ANTI-SPAM PARA EL CHECKOUT ---
if 'bloqueo_checkout' not in st.session_state:
    st.session_state.bloqueo_checkout = False

# ---------------- CONEXIÓN A MONGODB ----------------
@st.cache_resource
def init_connection():
    MONGO_URI = st.secrets["MONGO_URI"] 
    return pymongo.MongoClient(MONGO_URI)

client = init_connection()
db = client["bakugan_market"]
col_productos = db["productos"]
col_apartados = db["apartados"]
col_config = db["configuracion"] 
col_ventas = db["ventas"] 
col_carritos = db["carritos_temporales"] 
col_penal = db["penalizaciones"] 

# ---------------- MOTOR NUCLEAR EN RAM (CACHÉ) ----------------
@st.cache_data(ttl=600, show_spinner=False)
def obtener_configuraciones():
    promos = col_config.find_one({"_id": "promociones"})
    if not promos:
        promos = {
            "volumen": [{"id": str(uuid.uuid4())[:8], "categoria": "Carta", "min_piezas": 5, "precio_fijo": 40.0, "activa": True}],
            "monto": [{"id": str(uuid.uuid4())[:8], "min_total": 2000.0, "porcentaje": 10.0, "activa": True}],
            "promo_3x2": False,
            "promo_15_off": False,
            "envio_gratis": {"activa": False, "monto_minimo": 2500.0}
        }
        col_config.insert_one({"_id": "promociones", **promos})
    else:
        actualizar = False
        if "promo_3x2" not in promos:
            promos["promo_3x2"] = False
            actualizar = True
        if "promo_15_off" not in promos:
            promos["promo_15_off"] = False
            actualizar = True
        if "envio_gratis" not in promos:
            promos["envio_gratis"] = {"activa": False, "monto_minimo": 2500.0}
            actualizar = True
            
        if actualizar:
            col_config.update_one({"_id": "promociones"}, {"$set": promos})
            
    prefs = col_config.find_one({"_id": "sitio_prefs"})
    return promos, prefs

@st.cache_data(ttl=300, show_spinner=False)
def obtener_referencias():
    ref_doc = col_config.find_one({"_id": "referencias"})
    if not ref_doc:
        return []
    return ref_doc.get("imagenes", [])

@st.cache_data(ttl=300, show_spinner=False)
def cargar_catalogo_textos():
    items = list(col_productos.find({}, {"imagenes_b64": 0, "imagenes_detalle_b64": 0, "imagen_b64": 0}))
    for i in items: i["_id"] = str(i["_id"])
    return items

@st.cache_data(max_entries=2000, show_spinner=False)
def obtener_foto_mongo(prod_id_str):
    doc = col_productos.find_one({"_id": ObjectId(prod_id_str)}, {"imagenes_b64": 1, "imagenes_detalle_b64": 1, "imagen_b64": 1})
    return doc if doc else {}

def forzar_actualizacion():
    st.cache_data.clear()

config_promos, config_data = obtener_configuraciones()
fondo_b64 = config_data.get("fondo_b64") if config_data else None
logo_b64 = config_data.get("logo_b64") if config_data else None

# ---------------- SISTEMA ANTICAÍDAS ----------------
if 'session_id' not in st.session_state:
    st.session_state.session_id = st.query_params.get("sesion", str(uuid.uuid4())[:8])
    st.query_params["sesion"] = st.session_state.session_id

if 'ultima_actividad_carrito' not in st.session_state:
    st.session_state.ultima_actividad_carrito = hora_qro()

if 'carrito_inicializado' not in st.session_state:
    carrito_guardado = col_carritos.find_one({"_id": st.session_state.session_id})
    if carrito_guardado and (hora_qro() - carrito_guardado.get("fecha", hora_qro()) < timedelta(minutes=30)):
        st.session_state.carrito = carrito_guardado.get("items", [])
        st.session_state.ultima_actividad_carrito = carrito_guardado.get("fecha", hora_qro())
    else:
        st.session_state.carrito = []
    st.session_state.carrito_inicializado = True

if st.session_state.carrito and (hora_qro() - st.session_state.ultima_actividad_carrito > timedelta(minutes=30)):
    st.session_state.carrito = []
    st.session_state.ultima_actividad_carrito = hora_qro()
    col_carritos.delete_one({"_id": st.session_state.session_id})
    st.warning("⏳ Tu carrito expiró por 30 minutos de inactividad. Las piezas fueron liberadas para otros clientes.")

def guardar_carrito():
    st.session_state.ultima_actividad_carrito = hora_qro()
    col_carritos.update_one(
        {"_id": st.session_state.session_id},
        {"$set": {"items": st.session_state.carrito, "fecha": hora_qro()}},
        upsert=True
    )

def comprimir_imagen(img_file):
    img_bytes = img_file.getvalue()
    img = Image.open(io.BytesIO(img_bytes))
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
    img.thumbnail((800, 800))
    
    # --- SISTEMA DE PROTECCIÓN TIPO OF (MARCA DE AGUA) ---
    draw = ImageDraw.Draw(img)
    width, height = img.size
    texto = "© BAKU-MARKET - FOTO ORIGINAL"
    try: font = ImageFont.truetype("arial.ttf", 25)
    except: font = ImageFont.load_default()
        
    draw.rectangle([(0, height - 30), (width, height)], fill=(0, 0, 0, 180))
    draw.text((10, height - 25), texto, fill="white", font=font)

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=70)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

# --- LEEMOS SI ES EL JEFE DESDE EL INICIO PARA QUE NO LO BLOQUEE ---
es_admin_url = st.query_params.get("jefe") == "1"

# ---------------- PANTALLA DE BLOQUEO CON CHECKBOX OBLIGATORIO ----------------
if not st.session_state.welcome_shown and not es_admin_url:
    st.markdown("<h1 style='text-align:center;'>🚨 ¡Detente ahí, Bakubanda! 🚨</h1>", unsafe_allow_html=True)
    st.info("""
    ### 📖 ¿Cómo apartar tus piezas en Baku-Market?
    1. **Filtra o Busca:** Usa el menú lateral para encontrar tus Bakugans favoritos.
    2. **Añade al Carrito:** Da clic en "🛒 Añadir". Revisa si la pieza es *Perfecta* 🟢 o si tiene *Detalle* 🟠.
    **REGLA DE ORO:** ¡Pícale **SOLO UNA VEZ** al botón de añadir por cada pieza que quieras!
    3. **Elige tu Promo:** Si hay más de una promoción activa, elige cuál te conviene más (No son acumulables).
    4. **Confirma tu Compra:** Llena tus datos y manda el WhatsApp automático para congelar tus piezas. Tienes 30 mins para hacerlo.

    ---
    ### ⏱️ REGLAS DE APARTADO (¡Obligatorio leer!)
    * Para que tu apartado sea válido, debes dar un **anticipo del 10% del total**. Si no hay anticipo, las piezas se liberan para otros.
    * Una vez dado tu anticipo, cuentas con **4 días exactos (o la fecha establecida en tu ticket)** para liquidar tu pedido.
    * 🚨 **OJO:** En caso de dar el 10% y no liquidar en el tiempo establecido, **se pierden las piezas y el dinero del anticipo**. ¡Evita penalizaciones!
    """)
    
    acepto_reglas = st.checkbox("✅ Declaro que he leído y acepto las reglas de apartado y los tiempos límite.")
    
    if acepto_reglas:
        if st.button("🚀 ¡ENTENDIDO, QUIERO VER EL CATÁLOGO! 🔥", use_container_width=True, type="primary"):
            st.session_state.welcome_shown = True
            st.rerun()
    else:
        st.button("🚀 ¡ENTENDIDO, QUIERO VER EL CATÁLOGO! 🔥", use_container_width=True, type="primary", disabled=True)
        
    st.stop()

# ---------------- MODALES Y DIÁLOGOS ----------------
@st.dialog("📖 ¡Reglas y Cómo Comprar!")
def abrir_tutorial():
    st.markdown("""
    1. **Añade al Carrito:** Pícale "🛒 Añadir" **SOLO UNA VEZ** por pieza.
    2. **Elige tu Promo:** Selecciona la promoción que prefieras (no acumulables).
    3. **Confirma:** Manda el WhatsApp automático. (Tienes 30 mins antes de que expire el carrito).
    
    ### ⏱️ REGLAS DE APARTADO
    * Obligatorio **anticipo del 10%**.
    * Cuentas con **4 días exactos (o fecha establecida)** para liquidar.
    * 🚨 **Penalización:** Si no liquidas en tiempo y forma, **se pierden las piezas y el anticipo**.
    """)
    if st.button("Cerrar", use_container_width=True):
        st.rerun()

@st.dialog("⭐ Referencias de Clientes")
def abrir_referencias():
    refs = obtener_referencias()
    if not refs:
        st.info("Aún no he subido referencias, ¡pero muy pronto habrá muchas! 🔥")
    else:
        st.markdown("¡Gracias a todos por su confianza! Aquí te dejo algunas de nuestras entregas exitosas:")
        html_refs = '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px;">'
        for r in refs:
            html_refs += f'<img src="data:image/jpeg;base64,{r}" style="width: 100%; border-radius: 8px; object-fit: cover; pointer-events: none;">'
        html_refs += '</div>'
        st.markdown(html_refs, unsafe_allow_html=True)
    if st.button("Cerrar Ventana", use_container_width=True):
        st.rerun()

# --- VENTANA GIGANTE DE WHATSAPP BLINDADA ---
@st.dialog("✅ ¡Apartado Exitoso!")
def modal_whatsapp(enlace):
    st.success("Tus piezas ya están bloqueadas y apartadas en el sistema.")
    st.markdown("### 🚨 ¡Falta un último paso!")
    st.markdown("Para procesar tu pedido, es obligatorio enviarnos el mensaje de confirmación automático:")
    
    st.link_button("📲 ABRIR WHATSAPP AUTOMÁTICO", enlace, type="primary", use_container_width=True)
    
    st.markdown(f"""
    <div style="text-align: center; margin-top: 5px; margin-bottom: 15px;">
        <a href="{enlace}" target="_top" style="color: #25D366; font-weight: bold; text-decoration: underline;">
            👉 ¿El botón verde no te abre WhatsApp? Toca este enlace 👈
        </a>
    </div>
    """, unsafe_allow_html=True)
    
    with st.expander("🛠️ Si nada de lo anterior funciona (Opción Manual)"):
        st.markdown("Copia el texto de abajo y mándanoslo manualmente al número **446 287 9839**:")
        st.code(st.session_state.get('wa_texto_crudo', ''), language='text')
    
    st.warning("OJO: Recuerda que necesitas depositar el 10% de anticipo para que tu apartado sea válido. De lo contrario, podríamos llegar a cancelar tu pedido.")
    st.markdown("---")
    if st.button("Cerrar esta ventana (Ya envié mi mensaje)", use_container_width=True):
        if 'wa_link' in st.session_state: del st.session_state['wa_link']
        if 'wa_texto_crudo' in st.session_state: del st.session_state['wa_texto_crudo']
        st.rerun()

@st.dialog("🔍 Modo Detalle")
def abrir_zoom(nombre_prod, imagenes_b64):
    st.markdown(f"### {nombre_prod}")
    html_galeria = '<div class="galeria-container">'
    for img_b64 in imagenes_b64:
        html_galeria += f'<img src="data:image/jpeg;base64,{img_b64}" class="galeria-ampliada-img">'
    html_galeria += '</div>'
    st.markdown(html_galeria, unsafe_allow_html=True)
    if len(imagenes_b64) > 1:
        st.markdown("<p style='text-align: center; color: #aaa; font-size: 14px; margin-top: 10px;'>👉 Desliza para ver más</p>", unsafe_allow_html=True)

@st.dialog("🎁 Menú de Regalos (Promo 3x2)")
def modal_regalo_3x2():
    precio_max = 160.0
    st.markdown(f"¡Felicidades! Como llevas 2 piezas, tienes derecho a elegir una tercera completamente **GRATIS**.")
    st.info("👇 Estas son las piezas que aplican para tu regalo. ¡Elige rápido antes de que te la ganen!")
    
    tipos_con_atributo = ["Bakugan", "Trampa", "Vehículo", "Armamento", "BakuTech", "Set de Batalla", "Deka"]
    catalogo_ram = cargar_catalogo_textos()
    regalos = [p for p in catalogo_ram if p.get("tipo", "Bakugan") not in ["Carta", "BakuCore", "Extra"] and p.get("stock", 0) > 0 and p.get("precio", 0) <= precio_max]
    
    regalos_filtrados = []
    for r in regalos:
        f_lanz = r.get("fecha_lanzamiento")
        if isinstance(f_lanz, datetime) and f_lanz > hora_qro():
            continue
        regalos_filtrados.append(r)
        
    regalos_filtrados = sorted(regalos_filtrados, key=lambda x: x["precio"], reverse=True)[:50]
    
    if not regalos_filtrados:
        st.warning(f"Uy, parece que en este momento no tenemos piezas disponibles de ${precio_max} o menos.")
    else:
        for reg in regalos_filtrados:
            c1, c2 = st.columns([3, 1])
            
            emojis = ""
            if reg.get("tipo") in tipos_con_atributo and "atributo" in reg:
                attr1 = reg["atributo"].split()[-1] if " " in reg["atributo"] else ""
                attr2 = reg.get("atributo_2", "Ninguno")
                attr2_emoji = attr2.split()[-1] if " " in attr2 and attr2 != "Ninguno" else ""
                
                if attr2_emoji:
                    emojis = f"{attr1}/{attr2_emoji}🧬"
                elif reg.get("es_fusion"):
                    emojis = f"{attr1}🧬"
                else:
                    emojis = f"{attr1}"

            c1.markdown(f"<div style='margin-top:8px;'><span style='font-size:16px;'><b>{reg['nombre']}</b> {emojis}</span></div>", unsafe_allow_html=True)
            if c2.button("🎁 Elegir", key=f"btn_regalo_{str(reg['_id'])}", use_container_width=True):
                st.session_state.carrito.append({
                    "_id": str(reg["_id"]), "nombre": reg["nombre"],
                    "precio": reg["precio"], "variante": "normal", "tipo": reg.get("tipo", "Bakugan")
                })
                guardar_carrito()
                if "abrir_modal_3x2" in st.session_state: st.session_state.abrir_modal_3x2 = False
                st.rerun()
                
    st.markdown("---")
    if st.button("Elegir más tarde / Cerrar Menú", use_container_width=True):
        if "abrir_modal_3x2" in st.session_state: st.session_state.abrir_modal_3x2 = False
        st.rerun()

# --- AQUÍ ASEGURAMOS QUE SE DISPARE EL MODAL DEL WHATSAPP SI EXISTE EN MEMORIA ---
if 'wa_link' in st.session_state and st.session_state.wa_link:
    modal_whatsapp(st.session_state.wa_link)

# ---------------- MANTENIMIENTO AUTOMÁTICO ----------------
@st.cache_data(ttl=3600, show_spinner=False)
def ejecutar_mantenimiento(trigger):
    ahora = hora_qro()
    vencidos = list(col_apartados.find({"fecha_vencimiento": {"$lt": ahora}}))
    if vencidos:
        for doc in vencidos:
            campo = doc.get("campo_stock", "stock")
            col_productos.update_one({"_id": doc["producto_id"]}, {"$inc": {campo: 1}})
            if doc.get("anticipo", 0) > 0:
                col_penal.insert_one({
                    "cliente": doc.get("comprador_nombre", "Auto-Cancelado"),
                    "telefono": doc.get("comprador_telefono", "N/A"),
                    "productos": [doc.get("nombre_producto", "Desconocido")],
                    "monto_retenido": doc.get("anticipo", 0),
                    "fecha": hora_qro()
                })
            col_apartados.delete_one({"_id": doc["_id"]})
        forzar_actualizacion()
    
    limite_cart = hora_qro() - timedelta(minutes=30)
    col_carritos.delete_many({"fecha": {"$lt": limite_cart}})
    return True

ejecutar_mantenimiento(datetime.utcnow().strftime("%Y-%m-%d %H"))

# --- CSS EXTERMINADOR DEFINITIVO + AJUSTES COMPACTOS + BLINDAJE DE IMÁGENES ---
css_global = f"""
<style>
/* --- BLINDAJE ANTI-COPIA Y ANTI-DESCARGA --- */
img {{
    -webkit-user-drag: none !important;
    -webkit-touch-callout: none !important;
    pointer-events: none !important;
}}

header[data-testid="stHeader"] {{ background: transparent !important; box-shadow: none !important; visibility: visible !important; }}
[data-testid="collapsedControl"] {{ display: flex !important; visibility: visible !important; }}
.stDeployButton {{ display: none !important; }}
#MainMenu {{ display: none !important; }}
[data-testid="stToolbarActions"] {{ display: none !important; }}
footer {{ visibility: hidden !important; display: none !important; }}
#creatorBadge {{ display: none !important; opacity: 0 !important; }}
div[data-testid="viewerBadge"] {{ display: none !important; opacity: 0 !important; }}
div[class*="viewerBadge"] {{ display: none !important; opacity: 0 !important; }}
div[class*="CreatorBadge"] {{ display: none !important; opacity: 0 !important; }}
a[href*="streamlit.io/cloud"] {{ display: none !important; pointer-events: none !important; }}
iframe[title*="badge"] {{ display: none !important; opacity: 0 !important; pointer-events: none !important; }}
iframe[src*="badge"] {{ display: none !important; opacity: 0 !important; pointer-events: none !important; }}

.stApp {{
    {'background-image: url("data:image/png;base64,' + fondo_b64 + '");' if fondo_b64 else ''}
    background-size: cover; background-position: center; background-repeat: no-repeat; background-attachment: fixed;
}}
.block-container {{
    background-color: rgba(14, 17, 23, 0.85); 
    padding-top: 2.5rem !important; padding-right: 2rem; padding-bottom: 2rem; padding-left: 2rem;
    margin-top: 1rem; border-radius: 15px;
}}
.tarjeta-cliente {{
    background-color: rgba(255, 255, 255, 0.1); padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid #444;
}}
.galeria-container {{
    display: flex; overflow-x: auto; scroll-snap-type: x mandatory; gap: 0;
    -ms-overflow-style: none; scrollbar-width: none; border-radius: 8px; margin-bottom: 5px;
}}
.galeria-container::-webkit-scrollbar {{ display: none; }}
.galeria-img {{
    scroll-snap-align: center; flex: 0 0 100%; width: 100%; aspect-ratio: 1 / 1 !important; 
    object-fit: cover !important; border-radius: 8px; background-color: transparent; 
}}
.galeria-ampliada-img {{
    scroll-snap-align: center; flex: 0 0 100%; width: 100%; max-height: 65vh; 
    object-fit: contain !important; border-radius: 8px; background-color: transparent; 
}}
@media (max-width: 768px) {{
    .block-container {{ padding-top: 3.5rem !important; margin-top: 0rem; }}
    .stTextInput input {{ font-size: 16px !important; padding: 0.6rem !important; }}
    .stButton > button {{ font-size: 16px !important; padding: 0.5rem 1rem !important; min-height: 2.8rem !important; }}
    div[data-testid="stPopover"] > button {{ font-size: 16px !important; padding: 0.6rem 1rem !important; min-height: 2.8rem !important; }}
}}
</style>
"""
st.markdown(css_global, unsafe_allow_html=True)

# --- AURELUS AGREGADO A LAS CATEGORÍAS ---
categorias = ["Todos", "Pyrus 🔥", "Aquos 💧", "Ventus 🍃", "Darkus 🌑", "Haos ✨", "Subterra 🪨", "Aurelus 🟡"]
materiales = ["Todas", "Metálica", "Cartón"]
simbolos_core = ["Todos", "Fist ✊", "Flaming Fist 🔥✊", "Shield 🛡️", "Magic Shield ✨🛡️", "Helix 🧬"]
tipos_producto = ["Bakugan", "Trampa", "Carta", "BakuCore", "Vehículo", "Armamento", "BakuTech", "Extra", "Set de Batalla", "Deka"]
tipos_con_atributo = ["Bakugan", "Trampa", "Vehículo", "Armamento", "BakuTech", "Set de Batalla", "Deka"]

if logo_b64:
    st.sidebar.markdown(f'<style>.logo-celular {{ width: 100%; border-radius: 8px; margin-bottom: 10px; }} @media (max-width: 768px) {{ .logo-celular {{ width: 45%; margin-left: auto; margin-right: auto; display: block; }} }} </style> <img src="data:image/png;base64,{logo_b64}" class="logo-celular">', unsafe_allow_html=True)
else:
    st.sidebar.markdown("### 🛒 Mi Tienda")

# --- BOTÓN DE TUTORIAL Y REFERENCIAS ---
st.sidebar.markdown("---")
if st.sidebar.button("❓ Reglas / ¿Cómo apartar?", use_container_width=True):
    abrir_tutorial()
if st.sidebar.button("⭐ Mis Referencias", use_container_width=True):
    abrir_referencias()
st.sidebar.markdown("---")

st.sidebar.header("Filtros Avanzados")

def reset_limite():
    st.session_state.limite_items = 12

tipo_busqueda = st.sidebar.selectbox("¿Qué buscas?", ["Todo el Catálogo 🌍", "Bakugans 🔥", "Trampas 🪤", "Cartas 🃏", "BakuCores 🛑", "Vehículos 🏎️", "Armamentos ⚔️", "BakuTech 🦾", "Extras 🎁", "Sets de Batalla 🏟️", "Deka 🌐", "Piezas / Detalles 🛠️"], on_change=reset_limite)
tipos_con_atributo_ui = ["Bakugans 🔥", "Trampas 🪤", "Vehículos 🏎️", "Armamentos ⚔️", "BakuTech 🦾", "Sets de Batalla 🏟️", "Deka 🌐"]

if tipo_busqueda in tipos_con_atributo_ui: sub_filtro = st.sidebar.selectbox("Filtra por Atributo", categorias, on_change=reset_limite)
elif tipo_busqueda == "Cartas 🃏": sub_filtro = st.sidebar.selectbox("Filtra por Material", materiales, on_change=reset_limite)
elif tipo_busqueda == "BakuCores 🛑": sub_filtro = st.sidebar.selectbox("Filtra por Símbolo", simbolos_core, on_change=reset_limite)
else: sub_filtro = "Todos"

vista_admin = "Catálogo" 

if es_admin_url:
    st.sidebar.markdown("---")
    if not st.session_state.admin_autenticado:
        admin_input = st.sidebar.text_input("🔑 Acceso Admin", type="password")
        if admin_input == st.secrets["ADMIN_PASS"]:
            st.session_state.admin_autenticado = True
            st.rerun()
        elif admin_input != "":
            st.sidebar.error("Contraseña incorrecta.")
    
    if st.session_state.admin_autenticado:
        st.sidebar.success("¡Bienvenido, jefe!")
        if st.sidebar.button("🚪 Cerrar Sesión"):
            st.session_state.admin_autenticado = False
            st.rerun()
        vista_admin = st.sidebar.radio("Opciones de Administrador", ["Ver Catálogo", "❌ Agotados (Stock 0)", "⏳ Programados", "➕ Agregar Producto", "📋 Ver Apartados", "📊 Finanzas y Ventas", "🎨 Personalizar Página", "🎁 Gestor de Promociones", "⭐ Gestor de Referencias"])

st.sidebar.markdown("<div style='height: 400px;'></div>", unsafe_allow_html=True)

if vista_admin == "🎁 Gestor de Promociones":
    st.title("🎁 Gestor de Promociones")
    st.markdown("### ➕ Crear Nueva Promoción")
    with st.container():
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            with st.expander("📦 Descuento por Volumen (Categoría a Precio Fijo)"):
                cat_nueva = st.selectbox("Categoría que recibe el descuento", tipos_producto)
                min_p = st.number_input("Cantidad mínima de piezas para activar", min_value=1, value=5)
                prec_f = st.number_input("Precio especial c/u ($)", min_value=1.0, value=40.0)
                if st.button("Guardar Promo de Volumen"):
                    config_promos["volumen"].append({"id": str(uuid.uuid4())[:8], "categoria": cat_nueva, "min_piezas": min_p, "precio_fijo": prec_f, "activa": True})
                    col_config.update_one({"_id": "promociones"}, {"$set": config_promos})
                    forzar_actualizacion()
                    st.success("¡Promoción agregada!")
                    st.rerun()
        with col_t2:
            with st.expander("💰 Descuento por Monto Global (% de Descuento)"):
                min_t = st.number_input("Monto mínimo de compra ($)", min_value=1.0, value=2000.0)
                pct_d = st.number_input("Porcentaje de Descuento (%)", min_value=1, max_value=99, value=10)
                if st.button("Guardar Promo de Monto"):
                    config_promos["monto"].append({"id": str(uuid.uuid4())[:8], "min_total": min_t, "porcentaje": pct_d, "activa": True})
                    col_config.update_one({"_id": "promociones"}, {"$set": config_promos})
                    forzar_actualizacion()
                    st.success("¡Promoción agregada!")
                    st.rerun()
                    
    st.markdown("---")
    st.markdown("### 🟢 Promociones Registradas")
    cambios = False
    
    st.markdown("#### 🌟 Promoción Estática 3x2")
    c1_3x2, c2_3x2, _ = st.columns([6, 2, 2])
    c1_3x2.info("Llevas 3, pagas 2 *(Regalo Topado a $160.00)*")
    activa_3x2 = c2_3x2.toggle("Activada", value=config_promos.get("promo_3x2", False), key="tg_3x2")
    if activa_3x2 != config_promos.get("promo_3x2", False):
        config_promos["promo_3x2"] = activa_3x2
        cambios = True

    # --- NUEVA PROMO 15% OFF ---
    st.markdown("#### 🔥 Promoción Estática 15% OFF")
    c1_15, c2_15, _ = st.columns([6, 2, 2])
    c1_15.info("15% de descuento en la tienda *(No aplica en Cartas ni piezas con Detalle)*")
    activa_15 = c2_15.toggle("Activada", value=config_promos.get("promo_15_off", False), key="tg_15")
    if activa_15 != config_promos.get("promo_15_off", False):
        config_promos["promo_15_off"] = activa_15
        cambios = True

    st.markdown("#### 🚚 Envío Gratis")
    c1_env, c2_env, _ = st.columns([6, 2, 2])
    monto_env = config_promos.get("envio_gratis", {}).get("monto_minimo", 2500.0)
    c1_env.info(f"Envío gratis en compras desde **${monto_env:,.2f}**")
    activa_env = c2_env.toggle("Activada", value=config_promos.get("envio_gratis", {}).get("activa", False), key="tg_env")
    if activa_env != config_promos.get("envio_gratis", {}).get("activa", False):
        config_promos["envio_gratis"]["activa"] = activa_env
        config_promos["envio_gratis"]["monto_minimo"] = monto_env
        cambios = True

    if config_promos.get("volumen"):
        st.markdown("#### 📦 Promociones por Volumen Activas/Inactivas")
        for i, promo in enumerate(config_promos["volumen"]):
            c1, c2, c3 = st.columns([6, 2, 2])
            c1.info(f"Si llevan **{promo['min_piezas']} o más {promo['categoria']}s**, cuestan **${promo['precio_fijo']:,.2f} c/u**")
            activa = c2.toggle("Activada", value=promo["activa"], key=f"tg_v_{promo['id']}")
            if activa != promo["activa"]:
                config_promos["volumen"][i]["activa"] = activa
                cambios = True
            if c3.button("🗑️ Eliminar", key=f"dl_v_{promo['id']}"):
                config_promos["volumen"].pop(i)
                cambios = True
                
    if config_promos.get("monto"):
        st.markdown("#### 💰 Promociones por Monto Activas/Inactivas")
        for i, promo in enumerate(config_promos["monto"]):
            c1, c2, c3 = st.columns([6, 2, 2])
            c1.info(f"Si la compra es mayor a **${promo['min_total']:,.2f}**, aplicar **{promo['porcentaje']}% de descuento**")
            activa = c2.toggle("Activada", value=promo["activa"], key=f"tg_m_{promo['id']}")
            if activa != promo["activa"]:
                config_promos["monto"][i]["activa"] = activa
                cambios = True
            if c3.button("🗑️ Eliminar", key=f"dl_m_{promo['id']}"):
                config_promos["monto"].pop(i)
                cambios = True
                
    if cambios:
        col_config.update_one({"_id": "promociones"}, {"$set": config_promos})
        forzar_actualizacion()
        st.rerun()

elif vista_admin == "⭐ Gestor de Referencias":
    st.title("⭐ Gestor de Referencias")
    st.markdown("Sube capturas de pantalla, fotos de guías o clientes con sus paquetes para generar confianza en tus nuevos compradores.")
    
    nuevas_refs = st.file_uploader("📸 Subir nuevas referencias", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    if st.button("Guardar Referencias", type="primary"):
        if nuevas_refs:
            refs_b64 = [comprimir_imagen(img) for img in nuevas_refs]
            col_config.update_one({"_id": "referencias"}, {"$push": {"imagenes": {"$each": refs_b64}}}, upsert=True)
            forzar_actualizacion()
            st.success(f"¡{len(nuevas_refs)} referencias subidas con éxito!")
            st.rerun()
        else:
            st.warning("Selecciona al menos una imagen.")
            
    st.markdown("---")
    st.markdown("### 🖼️ Referencias Actuales")
    refs_actuales = obtener_referencias()
    if not refs_actuales:
        st.info("No hay referencias subidas actualmente.")
    else:
        cols = st.columns(4)
        for idx, ref in enumerate(refs_actuales):
            with cols[idx % 4]:
                st.markdown(f'<img src="data:image/jpeg;base64,{ref}" style="width:100%; border-radius:8px; margin-bottom:10px;">', unsafe_allow_html=True)
                if st.button("🗑️ Eliminar", key=f"del_ref_{idx}", use_container_width=True):
                    col_config.update_one({"_id": "referencias"}, {"$pull": {"imagenes": ref}})
                    forzar_actualizacion()
                    st.rerun()

elif vista_admin == "📊 Finanzas y Ventas":
    st.title("📊 Panel de Analítica Financiera")
    
    tab_ventas, tab_penalizaciones = st.tabs(["📦 Ventas Concretadas", "🚫 Penalizaciones (Ingresos Extra)"])
    
    with tab_ventas:
        ventas = list(col_ventas.find({}))
        if not ventas:
            st.info("Aún no tienes ventas registradas para analizar.")
        else:
            def calcular_metricas(lista_ventas):
                ingresos = sum((v.get("precio_total", 0) - v.get("deuda_restante", 0)) for v in lista_ventas)
                gastos = sum(v.get("gasto_envio", 0) for v in lista_ventas)
                return ingresos, gastos, ingresos - gastos
                
            col1, col2, col3, col4 = st.columns(4)
            datos_rango = [v for v in ventas if v["fecha_venta"] >= hora_qro() - timedelta(days=365)]
            ing, gas, gan = calcular_metricas(datos_rango)
            col1.metric("📦 Vendidas", len(datos_rango))
            col2.metric("💸 Cobrado Bruto", f"${ing:,.2f}")
            col3.metric("📉 Gastos", f"${gas:,.2f}")
            col4.metric("💰 Neta (En Bolsa)", f"${gan:,.2f}")
                    
            st.markdown("---")
            for v in reversed(ventas):
                deuda = v.get("deuda_restante", 0.0)
                neta = (v.get('precio_total', 0) - deuda) - v.get('gasto_envio', 0)
                cobro_envio = v.get('ingreso_envio', 0)
                gasto_envio = v.get('gasto_envio', 0)
                
                html_deuda = f'&nbsp;|&nbsp; 🔴 <b>Deuda: <span style="color: #e74c3c;">${deuda:,.2f}</span></b>' if deuda > 0 else ""
                
                st.markdown(f'<div class="tarjeta-cliente" style="margin-bottom: 5px;"><div style="font-size: 14px; margin-bottom: 5px;"><span style="color: #aaa;">📅 {v["fecha_venta"].strftime("%d/%m/%Y")}</span> &nbsp;|&nbsp; 👤 <b>{v["cliente"]}</b></div><div style="font-size: 15px; margin-bottom: 5px;">💰 <b>Ganancia Neta: <span style="color: #2ecc71;">${neta:,.2f}</span></b> &nbsp;|&nbsp; 📦 Cobro Envío: <span style="color: #f1c40f;">${cobro_envio:,.2f}</span> &nbsp;|&nbsp; 📉 Costo Guía: <span style="color: #e74c3c;">${gasto_envio:,.2f}</span>{html_deuda}</div><div style="font-size: 13px; color: #ccc;">📝 <i>Obs: {v.get("observaciones", "Ninguna")}</i></div></div>', unsafe_allow_html=True)
                
                with st.expander("✏️ Editar Venta / Liquidar Deuda", expanded=False):
                    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
                    with c1: e_cobro = st.number_input("Cobro Envío $", value=float(cobro_envio), step=10.0, key=f"ecob_{v['_id']}")
                    with c2: e_gasto = st.number_input("Costo Guía $", value=float(gasto_envio), step=10.0, key=f"egas_{v['_id']}")
                    with c3: e_deuda = st.number_input("Deuda Pendiente $", value=float(deuda), step=10.0, key=f"edeu_{v['_id']}", help="Si el cliente ya te pagó el resto, bájalo a $0.00")
                    with c4: e_obs = st.text_input("Observaciones / Guía", value=v.get("observaciones", ""), key=f"eobs_{v['_id']}")
                    
                    c_btn1, c_btn2 = st.columns(2)
                    if c_btn1.button("💾 Guardar Cambios", key=f"esave_{v['_id']}", use_container_width=True):
                        precio_base = v.get("precio_productos", v.get("precio_total", 0) - v.get("ingreso_envio", 0))
                        nuevo_precio_total = precio_base + e_cobro
                        col_ventas.update_one(
                            {"_id": v["_id"]},
                            {"$set": {
                                "ingreso_envio": e_cobro,
                                "gasto_envio": e_gasto,
                                "deuda_restante": e_deuda,
                                "observaciones": e_obs,
                                "precio_total": nuevo_precio_total,
                                "precio_productos": precio_base
                            }}
                        )
                        st.success("¡Venta actualizada exitosamente!")
                        st.rerun()
                        
                    if c_btn2.button("🗑️ Borrar Registro (Error)", key=f"edel_{v['_id']}", use_container_width=True, type="secondary"):
                        col_ventas.delete_one({"_id": v["_id"]})
                        st.success("Registro de venta eliminado correctamente.")
                        st.rerun()
                        
    with tab_penalizaciones:
        st.markdown("Aquí se refleja todo el dinero de anticipos que te quedaste por apartados no liquidados o cancelados. Esto suma a tus ganancias netas sin afectar el contador de piezas vendidas.")
        penalizaciones = list(col_penal.find({}).sort("fecha", -1))
        
        if not penalizaciones:
            st.info("No hay ingresos por apartados cancelados.")
        else:
            total_penal = sum(p.get("monto_retenido", 0) for p in penalizaciones)
            st.metric("💰 Total Ingresos por Penalizaciones", f"${total_penal:,.2f}")
            st.markdown("---")
            for p in penalizaciones:
                st.markdown(f"""
                <div class="tarjeta-cliente">
                    <b>📅 {p['fecha'].strftime('%d/%m/%Y')} | 👤 {p.get('cliente', 'Desconocido')} (WA: {p.get('telefono', 'N/A')})</b><br>
                    <span style='color: #2ecc71; font-weight: bold;'>Ganancia retenida (Anticipo): ${p.get('monto_retenido', 0):,.2f}</span><br>
                    <span style='font-size: 13px; color: #aaa;'>Piezas liberadas: {', '.join(p.get('productos', []))}</span>
                </div>
                """, unsafe_allow_html=True)
                if st.button("🗑️ Borrar", key=f"del_p_{p['_id']}"):
                    col_penal.delete_one({"_id": p["_id"]})
                    st.rerun()

elif vista_admin == "🎨 Personalizar Página":
    st.title("🎨 Personaliza el Diseño de tu Tienda")
    with st.form("form_personalizacion"):
        nuevo_fondo = st.file_uploader("Fondo de Pantalla HD", type=["png", "jpg", "jpeg"])
        nuevo_logo = st.file_uploader("Logo del Menú Lateral", type=["png", "jpg", "jpeg"])
        if st.form_submit_button("Guardar Diseño"):
            update_data = {}
            if nuevo_fondo: update_data["fondo_b64"] = base64.b64encode(nuevo_fondo.getvalue()).decode("utf-8")
            if nuevo_logo: update_data["logo_b64"] = base64.b64encode(nuevo_logo.getvalue()).decode("utf-8")
            if update_data:
                col_config.update_one({"_id": "sitio_prefs"}, {"$set": update_data}, upsert=True)
                forzar_actualizacion()
                st.success("¡Diseño actualizado! Recarga la página.")
                st.rerun()

elif vista_admin == "➕ Agregar Producto":
    st.title("🛠️ Agregar nuevo producto")
    tipo_prod = st.selectbox("Tipo de Producto", tipos_producto)
    nombre = st.text_input("Nombre / Descripción principal")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: atributo_form = st.selectbox("Atributo", categorias[1:], disabled=(tipo_prod not in tipos_con_atributo)) 
    with col2: atributo_2_form = st.selectbox("Atributo 2 (Fusión)", ["Ninguno"] + categorias[1:], disabled=(tipo_prod not in tipos_con_atributo))
    with col3: material_form = st.selectbox("Material", materiales[1:], disabled=(tipo_prod != "Carta"))
    with col4: simbolo_form = st.selectbox("Símbolo", simbolos_core[1:], disabled=(tipo_prod != "BakuCore"))
    
    st.markdown("### 🟢 Piezas Normales (Perfectas)")
    c_pn, c_sn = st.columns(2)
    with c_pn: precio = st.number_input("Precio Normal ($)", min_value=0.0, step=10.0)
    with c_sn: stock = st.number_input("Stock Normal", min_value=0, step=1, value=1)
    imagenes_subidas = st.file_uploader("📸 Sube fotos de la pieza NORMAL", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    
    st.markdown("### 🟠 Piezas con Detalles (Desperfectos)")
    con_detalle = st.checkbox("Activar versión con detalles / desperfectos")
    imagenes_detalle_subidas = []
    
    if con_detalle:
        c_pd, c_sd = st.columns(2)
        with c_pd: precio_detalle = st.number_input("Precio con Detalle ($)", min_value=0.0, step=10.0)
        with c_sd: stock_detalle = st.number_input("Stock con Detalle", min_value=0, step=1, value=1)
        detalle_prod = st.text_input("⚠️ Describe el desperfecto")
        imagenes_detalle_subidas = st.file_uploader("📸 Sube fotos SOLO mostrando el DETALLE", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    else:
        precio_detalle, stock_detalle, detalle_prod = 0.0, 0, ""
        
    st.markdown("### ⏳ Lanzamiento (Opcional)")
    con_lanzamiento = st.checkbox("Programar fecha y hora de publicación (Para drops automáticos)")
    fecha_final_prog = None
    if con_lanzamiento:
        c_lan1, c_lan2 = st.columns(2)
        fecha_lanz = c_lan1.date_input("Fecha de salida", min_value=hora_qro().date())
        hora_lanz = c_lan2.time_input("Hora exacta (Hora Centro)")
        fecha_final_prog = datetime.combine(fecha_lanz, hora_lanz)
    
    if st.button("Subir Producto al Catálogo"):
        if nombre and (imagenes_subidas or imagenes_detalle_subidas) and (precio > 0 or precio_detalle > 0):
            lista_imagenes_b64 = [comprimir_imagen(img) for img in imagenes_subidas[:6]] if imagenes_subidas else []
            lista_imagenes_detalle_b64 = [comprimir_imagen(img) for img in imagenes_detalle_subidas[:6]] if imagenes_detalle_subidas else []
            if con_detalle and not lista_imagenes_detalle_b64: lista_imagenes_detalle_b64 = lista_imagenes_b64
                
            nuevo_prod = {
                "tipo": tipo_prod, "nombre": nombre, "precio": precio, "stock": stock,
                "precio_detalle": precio_detalle, "stock_detalle": stock_detalle, "detalle": detalle_prod,
                "imagenes_b64": lista_imagenes_b64, "imagenes_detalle_b64": lista_imagenes_detalle_b64,
                "fecha_lanzamiento": fecha_final_prog
            }
            if tipo_prod in tipos_con_atributo: 
                nuevo_prod["atributo"] = atributo_form
                if atributo_2_form != "Ninguno":
                    nuevo_prod["atributo_2"] = atributo_2_form
                    
            elif tipo_prod == "Carta": nuevo_prod["material"] = material_form
            elif tipo_prod == "BakuCore": nuevo_prod["simbolo"] = simbolo_form
                
            col_productos.insert_one(nuevo_prod)
            forzar_actualizacion()
            st.success(f"¡{nombre} subido con éxito!")
            st.rerun() 
        else:
            st.error("Falta el nombre, subir foto o asignar precio.")

# --- SECCIÓN VER APARTADOS MODIFICADA CON LISTA COMPACTA ---
elif vista_admin == "📋 Ver Apartados":
    st.title("📋 Registro de Clientes y Apartados")
    todos_los_apartados = list(col_apartados.find({}))
    
    catalogo_ram_entero = cargar_catalogo_textos()
    diccionario_productos = {str(p["_id"]): p for p in catalogo_ram_entero}
    
    if not todos_los_apartados:
        st.info("No hay apartados activos.")
    else:
        clientes_dict = {}
        for ap in todos_los_apartados:
            tel = ap.get("comprador_telefono", "Sin número")
            if tel not in clientes_dict: clientes_dict[tel] = []
            clientes_dict[tel].append(ap)
        
        for tel, items in clientes_dict.items():
            nombre_cliente = items[0].get("comprador_nombre", "Desconocido")
            st.markdown(f'<div class="tarjeta-cliente"><h4>👤 {nombre_cliente} | 📞 WA: {tel}</h4>', unsafe_allow_html=True)
            total_cliente, total_anticipo = 0, 0
            fechas_venc, nombres_items = [], []
            
            for item in items:
                fecha_str = item["fecha_apartado"].strftime("%d/%m")
                precio_item = item.get("precio", 0.0)
                
                prod_id_str = str(item.get("producto_id", ""))
                prod_bd = diccionario_productos.get(prod_id_str, {})
                info_extra = ""
                color_attr = "#aaa"
                
                if prod_bd:
                    tipo_prod = prod_bd.get("tipo", "Bakugan")
                    if "atributo" in prod_bd and tipo_prod in tipos_con_atributo:
                        attr1 = prod_bd.get("atributo", "")
                        attr2 = prod_bd.get("atributo_2", "Ninguno")
                        info_extra = f"{attr1} / {attr2}" if attr2 != "Ninguno" else attr1
                        
                        if "Pyrus" in attr1: color_attr = "#e74c3c"
                        elif "Aquos" in attr1: color_attr = "#3498db"
                        elif "Ventus" in attr1: color_attr = "#2ecc71"
                        elif "Darkus" in attr1: color_attr = "#9b59b6"
                        elif "Haos" in attr1: color_attr = "#f1c40f"
                        elif "Subterra" in attr1: color_attr = "#e67e22"
                        elif "Aurelus" in attr1: color_attr = "#f39c12"
                        
                    elif "material" in prod_bd and tipo_prod == "Carta":
                        info_extra = prod_bd.get('material', '')
                    elif "simbolo" in prod_bd and tipo_prod == "BakuCore":
                        info_extra = prod_bd.get('simbolo', '')
                        
                separador = " | " if info_extra else ""
                info_html = f"<span style='color:{color_attr};'>{info_extra}</span>" if info_extra else ""
                variante_html = "🟠 (Detalle)" if item.get("campo_stock") == "stock_detalle" else "🟢 (Perfecta)"
                nombre_final = f"{item['nombre_producto']} {info_extra} {variante_html}" 
                
                total_cliente += precio_item
                total_anticipo += item.get("anticipo", 0.0)
                fechas_venc.append(item.get("fecha_vencimiento", hora_qro()))
                nombres_items.append(nombre_final) 
                
                c_ver, c_txt, c_del = st.columns([1, 9, 1])
                
                with c_ver:
                    if st.button("🖼️", key=f"ver_it_{item['_id']}", help="Ver foto"):
                        info_img = obtener_foto_mongo(prod_id_str)
                        imgs = info_img.get("imagenes_detalle_b64", []) if item.get("campo_stock") == "stock_detalle" else info_img.get("imagenes_b64", [])
                        if not imgs: imgs = info_img.get("imagenes_b64", [])
                        if imgs:
                            abrir_zoom(item['nombre_producto'], imgs)
                        else:
                            st.toast("No hay foto guardada para esta pieza ❌")
                            
                with c_txt:
                    st.markdown(f"<div style='margin-top: 5px; font-size: 16px;'>&bull; &nbsp;<b>{item['nombre_producto']}</b>{separador}{info_html} {variante_html} (${precio_item:,.2f}) <i>[Apt: {fecha_str}]</i></div>", unsafe_allow_html=True)
                    
                with c_del:
                    if st.button("❌", key=f"del_it_{item['_id']}", help="Quitar del pedido y regresar stock"):
                        campo = item.get("campo_stock", "stock")
                        col_productos.update_one({"_id": item["producto_id"]}, {"$inc": {campo: 1}})
                        col_apartados.delete_one({"_id": item["_id"]})
                        forzar_actualizacion()
                        st.rerun()
            
            fecha_max_venc = max(fechas_venc).strftime("%d/%m %H:%M")
            restante = total_cliente - total_anticipo
            
            st.markdown(f"**⏳ Vence el:** {fecha_max_venc}")
            st.markdown(f"**💰 Total pedido:** ${total_cliente:,.2f}")
            if total_anticipo > 0:
                st.markdown(f"**💸 Anticipo dado:** <span style='color:#f39c12;'>${total_anticipo:,.2f}</span>", unsafe_allow_html=True)
                st.markdown(f"**⚠️ Restante a cobrar:** <span style='color:#e74c3c; font-size:1.2em; font-weight:bold;'>${restante:,.2f}</span>", unsafe_allow_html=True)
            else:
                st.markdown(f"**⚠️ Total a cobrar:** <span style='color:#2ecc71; font-size:1.2em; font-weight:bold;'>${total_cliente:,.2f}</span>", unsafe_allow_html=True)
            
            col_conf, col_pro, col_canc, col_notif = st.columns(4)
            with col_conf:
                with st.expander("✅ Vender"):
                    if config_promos.get("envio_gratis", {}).get("activa", False) and total_cliente >= config_promos.get("envio_gratis", {}).get("monto_minimo", 2500.0):
                        st.success("🚚 ¡Este cliente califica para ENVÍO GRATIS!")
                        
                    st.markdown(f"<span style='font-size:14px; color:#aaa;'>Restante de piezas: ${restante:,.2f}</span>", unsafe_allow_html=True)
                    cobro_envio = st.number_input("Cobro Envío $", min_value=0.0, step=10.0, key=f"cobro_{tel}")
                    gastos = st.number_input("Costo Guía $", min_value=0.0, step=10.0, key=f"gasto_{tel}")
                    
                    total_hoy = restante + cobro_envio
                    pago_hoy = st.number_input("Pago recibido HOY $", value=float(total_hoy), min_value=0.0, step=10.0, key=f"pago_{tel}", help="¿Cuánto depositó ahorita? Si no liquidó completo, el resto se va a deuda.")
                    
                    obs = st.text_input("Obs / Guía", key=f"obs_{tel}")
                    
                    if st.button("Confirmar Venta / Envío", key=f"btn_venta_{tel}"):
                        deuda = total_hoy - pago_hoy
                        if deuda < 0: deuda = 0.0
                        
                        col_ventas.insert_one({
                            "cliente": nombre_cliente, "telefono": tel, "productos": nombres_items,
                            "precio_productos": total_cliente, "ingreso_envio": cobro_envio, "anticipo_previo": total_anticipo,
                            "precio_total": total_cliente + cobro_envio, "gasto_envio": gastos,
                            "deuda_restante": deuda,
                            "observaciones": obs, "fecha_venta": hora_qro()
                        })
                        for item in items: col_apartados.delete_one({"_id": item["_id"]})
                        forzar_actualizacion()
                        st.success("¡Venta y/o envío registrado!")
                        st.rerun()
                        
            with col_pro:
                with st.expander("⏳ Prórroga / Abono"):
                    nuevo_anticipo = st.number_input("Abonar $", min_value=0.0, step=50.0, key=f"ant_{tel}")
                    dias_pro = st.number_input("Días Extra", min_value=0, step=1, value=1, key=f"dias_{tel}")
                    if st.button("Aplicar", key=f"btn_pro_{tel}"):
                        ids_items = [item["_id"] for item in items]
                        if nuevo_anticipo > 0: col_apartados.update_one({"_id": ids_items[0]}, {"$inc": {"anticipo": nuevo_anticipo}})
                        if dias_pro > 0:
                            nueva_fecha = max(fechas_venc) + timedelta(days=dias_pro)
                            col_apartados.update_many({"_id": {"$in": ids_items}}, {"$set": {"fecha_vencimiento": nueva_fecha}})
                        forzar_actualizacion()
                        st.success("¡Prórroga aplicada!")
                        st.rerun()
                        
            with col_canc:
                with st.expander("🚫 Cancelar"):
                    if st.button("Confirmar Cancelación", key=f"btn_cancel_{tel}"):
                        if total_anticipo > 0:
                            col_penal.insert_one({
                                "cliente": nombre_cliente, "telefono": tel, "productos": nombres_items,
                                "monto_retenido": total_anticipo, "fecha": hora_qro()
                            })
                        for doc in items:
                            campo = doc.get("campo_stock", "stock")
                            col_productos.update_one({"_id": doc["producto_id"]}, {"$inc": {campo: 1}})
                            col_apartados.delete_one({"_id": doc["_id"]})
                        forzar_actualizacion()
                        st.success("¡Cancelado! El anticipo se movió a Penalizaciones.")
                        st.rerun()

            with col_notif:
                with st.expander("📱 Notificar"):
                    texto_bienvenida = f"¡Hola {nombre_cliente}! 👋 Te hablamos de Baku-Market. 🔥 Vimos que acabas de realizar tu apartado de {len(items)} piezas por un total de ${total_cliente:,.2f}. Te escribimos por aquí para confirmar tu pedido y pasarte los datos para el depósito del anticipo del 10%. ¡Gracias por tu confianza! 🐉"
                    texto_expiracion = f"Hola {nombre_cliente}, te escribo de Baku-Market. Te recuerdo que tu apartado de {len(items)} piezas (Restante: ${restante:,.2f}) vence el {fecha_max_venc}. ¿Gusta que revisemos un abono/prórroga o procesamos tu envío?"
                    texto_cancelacion = f"Hola {nombre_cliente}. Te notificamos que el tiempo de tu apartado concluyó en Baku-Market y tu pedido de {len(items)} piezas ha sido cancelado, liberando el stock. ¡Gracias por tu comprensión!"
                    
                    # --- ENLACES WA.ME UNIVERSALES Y SEGUROS ---
                    st.markdown(f'<a href="https://wa.me/52{tel.replace(" ", "")}?text={urllib.parse.quote(texto_bienvenida)}" target="_blank" style="color: #3498db; text-decoration: none;">👋 <b>Mensaje de Bienvenida</b></a>', unsafe_allow_html=True)
                    st.markdown(f'<br><a href="https://wa.me/52{tel.replace(" ", "")}?text={urllib.parse.quote(texto_expiracion)}" target="_blank" style="color: #f39c12; text-decoration: none;">⚠️ <b>Aviso Expiración</b></a>', unsafe_allow_html=True)
                    st.markdown(f'<br><a href="https://wa.me/52{tel.replace(" ", "")}?text={urllib.parse.quote(texto_cancelacion)}" target="_blank" style="color: #e74c3c; text-decoration: none;">🚫 <b>Aviso Cancelación</b></a>', unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

else:
    es_modo_admin_catalogo = st.session_state.admin_autenticado and vista_admin == "Ver Catálogo"
    es_modo_admin_agotados = st.session_state.admin_autenticado and vista_admin == "❌ Agotados (Stock 0)"
    es_modo_admin_programados = st.session_state.admin_autenticado and vista_admin == "⏳ Programados"
    es_modo_edicion = es_modo_admin_catalogo or es_modo_admin_agotados or es_modo_admin_programados
    catalogo_ram_entero = cargar_catalogo_textos()
    
    if es_modo_edicion:
        if es_modo_admin_catalogo:
            st.title("🛠️ Administrar Catálogo e Inventario")
        elif es_modo_admin_agotados:
            st.title("❌ Piezas Agotadas (Restock)")
        elif es_modo_admin_programados:
            st.title("⏳ Drops Programados")
            
        total_publicaciones = len(catalogo_ram_entero)
        total_piezas_fisicas = sum(p.get("stock", 0) + p.get("stock_detalle", 0) for p in catalogo_ram_entero)
        valor_estimado_total = sum((p.get("stock", 0) * p.get("precio", 0.0)) + (p.get("stock_detalle", 0) * p.get("precio_detalle", 0.0)) for p in catalogo_ram_entero)
        
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("📦 Publicaciones Totales", total_publicaciones)
        col_m2.metric("🔢 Piezas Físicas", total_piezas_fisicas)
        col_m3.metric("💰 Valor Inventario", f"${valor_estimado_total:,.2f}")
        st.markdown("---")
        busqueda_texto = st.text_input("🔍 Buscar pieza por nombre...")
    else:
        # --- MENÚ DE SELECCIÓN DE PROMOS (MUTUAMENTE EXCLUSIVAS) ---
        texto_default = "Ninguna / Solo Envío Gratis" if config_promos.get("envio_gratis", {}).get("activa", False) else "Ninguna"
        opciones_promo = [texto_default]
        if config_promos.get("promo_3x2", False): opciones_promo.append("🌟 Súper 3x2")
        if config_promos.get("promo_15_off", False): opciones_promo.append("🔥 15% OFF")
        if config_promos.get("volumen", []) and any(p["activa"] for p in config_promos["volumen"]): opciones_promo.append("📦 Precio por Volumen")
        if config_promos.get("monto", []) and any(p["activa"] for p in config_promos["monto"]): opciones_promo.append("🤑 Descuento por Monto")

        # --- RENDERIZADO DEL CATÁLOGO PARA USUARIOS ---
        col_tit, col_busc, col_cart = st.columns([1.5, 2, 1.5])
        with col_tit: st.markdown("### 🔥 Baku-Market") 
        with col_busc: busqueda_texto = st.text_input("Buscar", placeholder="🔍 Buscar...", label_visibility="collapsed")
        
        st.markdown("---")
        if len(opciones_promo) > 1:
            st.markdown("##### 🏷️ Elige tu promoción (No son acumulables):")
            promo_seleccionada = st.radio("promos", opciones_promo, horizontal=True, label_visibility="collapsed")
        else:
            promo_seleccionada = texto_default
        st.markdown("---")

        # ---------------- EVALUAR PROMOS Y BANNER 3x2 / 15% OFF INTERACTIVO ----------------
        if promo_seleccionada == "🌟 Súper 3x2":
            elegibles_3x2 = [i for i in st.session_state.carrito if i.get("tipo") not in ["Carta", "BakuCore", "Extra"] and i.get("variante") != "detalle"]
            if len(elegibles_3x2) > 0 and len(elegibles_3x2) % 3 == 2:
                if st.session_state.get("abrir_modal_3x2", False): modal_regalo_3x2()
                st.markdown(f"""
                <div style="background: linear-gradient(90deg, #f1c40f, #f39c12); padding: 15px; border-radius: 8px; text-align: center; color: white; margin-bottom: 10px;">
                    <h3 style="margin: 0; color: white;">🎁 ¡Tienes un 3x2 Activo!</h3>
                    <p style="margin: 0; font-size: 16px;">Llevas 2 piezas, te regalamos la 3ra</p>
                </div>
                """, unsafe_allow_html=True)
                if st.button("👉 ABRIR MENÚ PARA ELEGIR MI REGALO 👈", type="primary", use_container_width=True):
                    st.session_state.abrir_modal_3x2 = True
                    st.rerun()
                    
        if promo_seleccionada == "🔥 15% OFF":
            st.markdown(f"""
            <div style="background: linear-gradient(90deg, #e74c3c, #c0392b); padding: 15px; border-radius: 8px; text-align: center; color: white; margin-bottom: 10px;">
                <h3 style="margin: 0; color: white;">🔥 ¡Tienes 15% de Descuento!</h3>
                <p style="margin: 0; font-size: 16px;">Se aplica en automático a tus piezas aplicables (Excluye Cartas y Detalles)</p>
            </div>
            """, unsafe_allow_html=True)

        # --- CARRITO INTELIGENTE CON CANDADOS DE PROMOS ---
        with col_cart:
            cantidad_carrito = len(st.session_state.carrito)
            items_procesados = [{"item": item, "precio_efec": item['precio'], "es_promo_vol": False, "es_promo_3x2": False, "es_promo_15": False, "msg_wa": ""} for item in st.session_state.carrito]
            conteo_categorias = {}
            textos_promos_activas = []
            
            for ip in items_procesados:
                t = ip["item"].get("tipo", "Bakugan")
                conteo_categorias[t] = conteo_categorias.get(t, 0) + 1
                
            promos_volumen_aplicables = {}
            mejor_promo_monto = None
            
            if promo_seleccionada == "📦 Precio por Volumen":
                for p_vol in config_promos.get("volumen", []):
                    if p_vol["activa"] and conteo_categorias.get(p_vol["categoria"], 0) >= p_vol["min_piezas"]:
                        promos_volumen_aplicables[p_vol["categoria"]] = p_vol["precio_fijo"]
                        textos_promos_activas.append(f"🎉 ¡Promo: {p_vol['min_piezas']}+ {p_vol['categoria']}s a ${p_vol['precio_fijo']:,.2f} c/u!")
                        
                for ip in items_procesados:
                    t = ip["item"].get("tipo", "Bakugan")
                    if t in promos_volumen_aplicables and ip['item']['precio'] > promos_volumen_aplicables[t]:
                        ip["precio_efec"] = promos_volumen_aplicables[t]
                        ip["es_promo_vol"] = True
                        
            if promo_seleccionada == "🔥 15% OFF":
                piezas_con_descuento = 0
                for ip in items_procesados:
                    if ip["item"].get("tipo") != "Carta" and ip["item"].get("variante") != "detalle":
                        ip["precio_efec"] = ip["precio_efec"] * 0.85
                        ip["es_promo_15"] = True
                        piezas_con_descuento += 1
                        
                if piezas_con_descuento > 0:
                    textos_promos_activas.append(f"🔥 ¡15% de descuento aplicado a {piezas_con_descuento} pieza(s)!")
                else:
                    textos_promos_activas.append("⚠️ Tu promo de 15% está activa, pero requiere piezas perfectas (excluye cartas).")
                    
            if promo_seleccionada == "🌟 Súper 3x2":
                elegibles_todas = [ip for ip in items_procesados if ip["item"].get("tipo", "Bakugan") not in ["Carta", "BakuCore", "Extra"] and ip["item"].get("variante", "normal") != "detalle"]
                max_regalos = len(elegibles_todas) // 3
                
                # CANDADO DE TITANIO: Solo las piezas de 160 o menos pueden ser regaladas.
                elegibles_regalables = sorted([ip for ip in elegibles_todas if ip["precio_efec"] <= 160.0], key=lambda x: x["precio_efec"], reverse=True)
                
                piezas_regaladas = 0
                for ip in elegibles_regalables:
                    if piezas_regaladas < max_regalos:
                        ip["precio_efec"] = 0.0
                        ip["es_promo_3x2"] = True
                        piezas_regaladas += 1
                        
                if piezas_regaladas > 0: 
                    textos_promos_activas.append(f"🌟 ¡Promo 3x2 Aplicada! ({piezas_regaladas} pieza(s) gratis)")
                elif max_regalos > 0 and piezas_regaladas == 0:
                    textos_promos_activas.append("⚠️ Tienes derecho a un regalo, elige uno de esta pagina")
            
            subtotal_previo = sum(ip["precio_efec"] for ip in items_procesados)
            mejor_pct = 0
            
            if promo_seleccionada == "🤑 Descuento por Monto":
                for p_mon in config_promos.get("monto", []):
                    if p_mon["activa"] and subtotal_previo >= p_mon["min_total"] and p_mon["porcentaje"] > mejor_pct:
                        mejor_pct = p_mon["porcentaje"]
                        mejor_promo_monto = p_mon
                if mejor_promo_monto: textos_promos_activas.append(f"🤑 ¡{mejor_promo_monto['porcentaje']}% OFF en tu carrito mayor a ${mejor_promo_monto['min_total']:,.2f}!")
                
            total_carrito = 0
            for ip in items_procesados:
                if ip["es_promo_3x2"]: ip["precio_final"], ip["msg_wa"] = 0.0, " (¡Gratis 3x2!)"
                elif ip["es_promo_15"]: ip["precio_final"], ip["msg_wa"] = ip["precio_efec"], " (-15%)"
                elif ip["es_promo_vol"]: ip["precio_final"], ip["msg_wa"] = ip["precio_efec"], f" (Promo ${ip['precio_efec']})"
                elif mejor_promo_monto: ip["precio_final"], ip["msg_wa"] = ip["precio_efec"] * (1 - (mejor_promo_monto["porcentaje"] / 100.0)), f" (-{mejor_promo_monto['porcentaje']}%)"
                else: ip["precio_final"], ip["msg_wa"] = ip["precio_efec"], ""
                total_carrito += ip["precio_final"]
                
            # --- AVISO VISUAL DE ENVÍO GRATIS ---
            promo_envio = config_promos.get("envio_gratis", {})
            if promo_envio.get("activa", False) and total_carrito >= promo_envio.get("monto_minimo", 2500.0):
                textos_promos_activas.append("🚚 ¡Felicidades! Tu compra califica para ENVÍO GRATIS.")
            
            with st.popover(f"🛒 Carrito ({cantidad_carrito}) - ${total_carrito:,.2f}", use_container_width=True):
                if cantidad_carrito > 0:
                    for txt in textos_promos_activas: st.success(txt)
                    for i, ip in enumerate(items_procesados):
                        c1, c2 = st.columns([4, 1])
                        item = ip["item"]
                        texto_precio = f"~~${item['precio']}~~ **${ip['precio_final']:,.2f}**" if ip["precio_final"] < item['precio'] else f"**${ip['precio_final']:,.2f}**"
                        if ip["precio_final"] == 0.0: texto_precio = f"~~${item['precio']}~~ **¡GRATIS!**"
                        c1.markdown(f"<span style='font-size:0.9em;'>{item['nombre']} - {texto_precio}</span>", unsafe_allow_html=True)
                        if c2.button("❌", key=f"del_cart_{i}_{item['_id']}"):
                            st.session_state.carrito.pop(i)
                            guardar_carrito() 
                            st.rerun()
                            
                    st.markdown("---")
                    st.markdown(f"**Total a pagar: ${total_carrito:,.2f}**")
                    nom = st.text_input("Tu Nombre", key="checkout_nom")
                    tel = st.text_input("Tu WhatsApp", key="checkout_tel")
                    
                    if st.button("Confirmar Apartado", use_container_width=True, type="primary"):
                        if st.session_state.bloqueo_checkout:
                            pass
                        elif nom and tel:
                            st.session_state.bloqueo_checkout = True
                            
                            if len(st.session_state.carrito) == 0:
                                st.session_state.bloqueo_checkout = False
                                st.rerun()
                                
                            error_stock = False
                            nombres_agotados = []
                            for ip in items_procesados:
                                item_bd = ip["item"]
                                db_prod = col_productos.find_one({"_id": ObjectId(item_bd["_id"])})
                                campo_stock = "stock_detalle" if item_bd.get("variante") == "detalle" else "stock"
                                if not db_prod or db_prod.get(campo_stock, 0) <= 0:
                                    error_stock = True
                                    nombres_agotados.append(item_bd["nombre"])
                            
                            if error_stock:
                                st.error(f"⚠️ ¡Uy! Alguien te ganó estas piezas mientras las tenías en el carrito: {', '.join(nombres_agotados)}. Quítalas pulsando la '❌' para confirmar el resto.")
                                st.session_state.bloqueo_checkout = False
                            else:
                                for ip in items_procesados:
                                    item_bd = ip["item"]
                                    item_bd_id = ObjectId(item_bd["_id"])
                                    db_prod = col_productos.find_one({"_id": item_bd_id})
                                    campo_stock = "stock_detalle" if item_bd.get("variante") == "detalle" and "stock_detalle" in db_prod else "stock"
                                    col_apartados.insert_one({
                                        "producto_id": item_bd_id, "nombre_producto": item_bd["nombre"],
                                        "precio": ip["precio_final"], "comprador_nombre": nom, "comprador_telefono": tel,
                                        "fecha_apartado": hora_qro(), "fecha_vencimiento": hora_qro() + timedelta(days=4), "campo_stock": campo_stock, "anticipo": 0.0
                                    })
                                    col_productos.update_one({"_id": item_bd_id}, {"$inc": {campo_stock: -1}})
                                
                                texto_crudo = f"Hola, soy {nom}. Acabo de apartar {cantidad_carrito} piezas por un total de ${total_carrito:,.2f}.\n\nMis piezas son:\n"
                                for ip in items_procesados: texto_crudo += f"👉 {ip['item']['nombre']} (${ip['precio_final']:,.2f}){ip['msg_wa']}\n"
                                
                                if not promo_seleccionada.startswith("Ninguna"):
                                    texto_crudo += f"\n*Nota: Seleccioné usar la promoción: {promo_seleccionada}.*"
                                
                                if promo_envio.get("activa", False) and total_carrito >= promo_envio.get("monto_minimo", 2500.0):
                                    texto_crudo += f"\n\n🚚 *Nota extra: ¡Mi pedido califica para ENVÍO GRATIS!*"
                                    
                                texto_crudo += f"\n\n⏱️ *Nota: Estoy consciente de que cuento con 4 días exactos (o la fecha establecida en mi ticket) para liquidar mi pedido y no perder mi apartado ni el anticipo del 10%.*"

                                # --- AQUÍ GUARDAMOS EL TEXTO EN MEMORIA POR SI EL BOTÓN FALLA ---
                                st.session_state.wa_texto_crudo = texto_crudo
                                st.session_state.wa_link = f"https://wa.me/524462879839?text={urllib.parse.quote(texto_crudo)}"
                                
                                st.session_state.carrito = [] 
                                st.session_state.bloqueo_checkout = False
                                guardar_carrito()
                                forzar_actualizacion()
                                st.rerun()
                        else: st.warning("⚠️ Faltan datos.")
                else: st.info("Carrito vacío.")

        banner_frases = []
        if config_promos.get("promo_3x2", False): banner_frases.append("🌟 <b>¡SÚPER 3x2! Llevas 3, Pagas 2</b>")
        if config_promos.get("promo_15_off", False): banner_frases.append("🔥 <b>15% OFF</b>")
        for p in config_promos.get("volumen", []):
            if p["activa"]: banner_frases.append(f"📦 <b>{p['min_piezas']}+ {p['categoria']}s a ${p['precio_fijo']:,.2f} c/u</b>")
        for p in config_promos.get("monto", []):
            if p["activa"]: banner_frases.append(f"🤑 <b>{p['porcentaje']}% OFF</b> en compras > ${p['min_total']:,.2f}")
        
        # --- ENVÍO GRATIS LIGADO EN LA BARRA DE PROMOS DE FORMA DINÁMICA ---
        if config_promos.get("envio_gratis", {}).get("activa", False):
            m_env = config_promos["envio_gratis"].get("monto_minimo", 2500.0)
            banner_frases.append(f"🚚 <b>ENVÍO GRATIS en compras >= ${m_env:,.2f}</b>")
                
        if banner_frases:
            st.markdown(f"""
            <div style="background: linear-gradient(90deg, #ff416c, #ff4b2b); padding: 12px; border-radius: 8px; text-align: center; color: white; font-size: 15px; margin-bottom: 20px;">
                ✨ <b>¡PROMOS ACTIVAS!</b> ✨ <br class="mobile-break"> {" &nbsp;|&nbsp; ".join(banner_frases)}
            </div>
            <style>@media (min-width: 768px) {{ .mobile-break {{ display: none; }} }}</style>
            """, unsafe_allow_html=True)

    # ---------------- BÚSQUEDA SÚPER RÁPIDA EN RAM ----------------
    productos_filtrados = []
    busqueda_low = busqueda_texto.lower() if busqueda_texto else ""

    for prod in catalogo_ram_entero:
        if busqueda_low and busqueda_low not in prod.get("nombre", "").lower(): continue

        tipo_p = prod.get("tipo", "Bakugan")
        incluir = True

        if tipo_busqueda in tipos_con_atributo_ui:
            if tipo_busqueda == "Bakugans 🔥" and tipo_p != "Bakugan" and "tipo" in prod: incluir = False
            elif tipo_busqueda == "Trampas 🪤" and tipo_p != "Trampa": incluir = False
            elif tipo_busqueda == "Vehículos 🏎️" and tipo_p != "Vehículo": incluir = False
            elif tipo_busqueda == "Armamentos ⚔️" and tipo_p != "Armamento": incluir = False
            elif tipo_busqueda == "BakuTech 🦾" and tipo_p != "BakuTech": incluir = False
            elif tipo_busqueda == "Sets de Batalla 🏟️" and tipo_p != "Set de Batalla": incluir = False
            elif tipo_busqueda == "Deka 🌐" and tipo_p != "Deka": incluir = False
            
            if incluir and sub_filtro != "Todos":
                if prod.get("atributo", "") != sub_filtro and prod.get("atributo_2", "Ninguno") != sub_filtro:
                    incluir = False
                    
        elif tipo_busqueda == "Cartas 🃏":
            if tipo_p != "Carta": incluir = False
            if incluir and sub_filtro != "Todas" and prod.get("material", "") != sub_filtro: incluir = False
        elif tipo_busqueda == "BakuCores 🛑":
            if tipo_p != "BakuCore": incluir = False
            if incluir and sub_filtro != "Todos" and prod.get("simbolo", "") != sub_filtro: incluir = False
        elif tipo_busqueda == "Extras 🎁":
            if tipo_p != "Extra": incluir = False

        if not incluir: continue

        stock_normal = prod.get('stock', 0)
        stock_detalle = prod.get('stock_detalle', 0)
        texto_detalle = prod.get('detalle', "")
        
        if texto_detalle and 'stock_detalle' not in prod:
            stock_detalle, stock_normal = stock_normal, 0
            
        es_agotado = (stock_normal == 0 and stock_detalle == 0)
        
        fecha_lanz = prod.get("fecha_lanzamiento")
        es_futuro = isinstance(fecha_lanz, datetime) and fecha_lanz > hora_qro()

        if es_modo_admin_programados:
            if es_futuro: productos_filtrados.append(prod)
            continue
            
        if es_futuro: continue 

        if es_modo_admin_agotados:
            if es_agotado: productos_filtrados.append(prod)
            continue
            
        if es_modo_admin_catalogo:
            if es_agotado: continue
            if tipo_busqueda == "Piezas / Detalles 🛠️" and not texto_detalle: continue
            if tipo_busqueda != "Piezas / Detalles 🛠️" and tipo_busqueda != "Todo el Catálogo 🌍" and texto_detalle and stock_normal == 0 and stock_detalle > 0: continue
            productos_filtrados.append(prod)
        else:
            if tipo_busqueda == "Piezas / Detalles 🛠️":
                if texto_detalle and stock_detalle > 0: productos_filtrados.append(prod)
            elif tipo_busqueda == "Todo el Catálogo 🌍":
                if not es_agotado: productos_filtrados.append(prod)
            else:
                if stock_normal > 0: productos_filtrados.append(prod)

    productos_filtrados.sort(key=lambda x: str(x["_id"]), reverse=True)

    agrupados = defaultdict(list)
    for p in productos_filtrados:
        clave_mezcla = p.get("atributo", p.get("tipo", "Otro"))
        agrupados[clave_mezcla].append(p)

    # --- BLINDAJE ANTI-CICLOS INFINITOS ---
    mezclados = []
    contador_seguridad = 0
    while agrupados and contador_seguridad < 5000:
        contador_seguridad += 1
        for clave in list(agrupados.keys()):
            if agrupados[clave]:
                mezclados.append(agrupados[clave].pop(0))
            if not agrupados[clave]:
                del agrupados[clave]
                
    productos_filtrados = mezclados

    # ---------------- RENDERIZADO PRINCIPAL (DIVIDIDO POR PESTAÑAS) ----------------
    productos_a_mostrar = productos_filtrados[:st.session_state.limite_items]

    if not productos_filtrados:
        if es_modo_admin_agotados:
            st.info("¡Felicidades jefe! No tienes ninguna pieza agotada en tu inventario.")
        elif es_modo_admin_programados:
            st.info("No hay drops programados a futuro.")
        else:
            st.info("No encontramos piezas en esta categoría.")
    else:
        # --- RENDERIZADO EXCLUSIVO PARA PROGRAMADOS (LISTA COMPACTA AGRUPADA) ---
        if es_modo_admin_programados:
            st.markdown("<br>", unsafe_allow_html=True)
            agrupados_prog = defaultdict(list)
            for p in productos_a_mostrar:
                f = p.get("fecha_lanzamiento")
                if not isinstance(f, datetime): f = hora_qro()
                agrupados_prog[f].append(p)
            
            for f_lanz in sorted(agrupados_prog.keys()):
                fecha_str = f_lanz.strftime('%d/%m/%Y a las %I:%M %p')
                st.markdown(f"""
                <div style="background-color: rgba(52, 152, 219, 0.15); padding: 8px 15px; border-radius: 5px; margin-top: 20px; margin-bottom: 10px; border-left: 4px solid #3498db;">
                    <b style="color: #3498db; font-size: 16px;">⏳ Sale el: {fecha_str}</b>
                </div>
                """, unsafe_allow_html=True)
                
                for prod in agrupados_prog[f_lanz]:
                    tipo_real = prod.get("tipo", "Bakugan")
                    info_extra = ""
                    color_attr = "#aaa"
                    if "atributo" in prod and tipo_real in tipos_con_atributo:
                        attr1 = prod.get("atributo", "")
                        attr2 = prod.get("atributo_2", "Ninguno")
                        info_extra = f"{attr1} / {attr2}" if attr2 != "Ninguno" else attr1
                        if "Pyrus" in attr1: color_attr = "#e74c3c"
                        elif "Aquos" in attr1: color_attr = "#3498db"
                        elif "Ventus" in attr1: color_attr = "#2ecc71"
                        elif "Darkus" in attr1: color_attr = "#9b59b6"
                        elif "Haos" in attr1: color_attr = "#f1c40f"
                        elif "Subterra" in attr1: color_attr = "#e67e22"
                        elif "Aurelus" in attr1: color_attr = "#f39c12"
                        
                    separador = " | " if info_extra else ""
                    info_html = f"<span style='color:{color_attr};'>{info_extra}</span>" if info_extra else ""
                    
                    st.markdown(f"<div style='font-size: 16px; margin-left: 10px; margin-bottom: 5px;'>&bull; &nbsp;<b>{prod['nombre']}</b>{separador}{info_html} (${prod.get('precio', 0):,.2f})</div>", unsafe_allow_html=True)
                    
                    with st.expander("✏️ Editar Drop"):
                        nuevo_nombre = st.text_input("Nombre del Producto", value=prod['nombre'], key=f"enom_{prod['_id']}")
                        idx_tipo = tipos_producto.index(tipo_real) if tipo_real in tipos_producto else 0
                        nuevo_tipo = st.selectbox("Categoría / Tipo", tipos_producto, index=idx_tipo, key=f"etipo_{prod['_id']}")

                        attr_actual = prod.get('atributo', categorias[1]) 
                        try: idx_attr = categorias[1:].index(attr_actual)
                        except ValueError: idx_attr = 0
                        
                        attr2_actual = prod.get('atributo_2', "Ninguno") 
                        try: idx_attr2 = (["Ninguno"] + categorias[1:]).index(attr2_actual)
                        except ValueError: idx_attr2 = 0

                        c_a1, c_a2 = st.columns(2)
                        with c_a1: nuevo_atributo = st.selectbox("Atributo", categorias[1:], index=idx_attr, key=f"eattr_{prod['_id']}")
                        with c_a2: nuevo_atributo_2 = st.selectbox("Atributo 2 (Fusión)", ["Ninguno"] + categorias[1:], index=idx_attr2, key=f"eattr2_{prod['_id']}")

                        np = st.number_input("Precio N.", value=float(prod.get('precio', 0)), step=10.0, key=f"epn_{prod['_id']}")
                        ns = st.number_input("Stock N.", value=int(prod.get('stock', 0)), step=1, key=f"esn_{prod['_id']}")
                        ndp = st.number_input("Precio D.", value=float(prod.get('precio_detalle', 0)), step=10.0, key=f"epd_{prod['_id']}")
                        nds = st.number_input("Stock D.", value=int(prod.get('stock_detalle', 0)), step=1, key=f"esd_{prod['_id']}")
                        ndtxt = st.text_input("Detalle", value=prod.get('detalle', ""), key=f"etxt_{prod['_id']}")
                        
                        es_prog_ed = st.checkbox("⏳ Programar lanzamiento", value=True, key=f"prog_{prod['_id']}")
                        fecha_final_ed = None
                        if es_prog_ed:
                            f_val = f_lanz.date()
                            h_val = f_lanz.time()
                            c_f, c_h = st.columns(2)
                            f_ed = c_f.date_input("Fecha", value=f_val, key=f"fed_{prod['_id']}")
                            h_ed = c_h.time_input("Hora", value=h_val, key=f"hed_{prod['_id']}")
                            fecha_final_ed = datetime.combine(f_ed, h_ed)
                        
                        c_bs, c_bd = st.columns(2)
                        if c_bs.button("💾 Guardar", key=f"save_{prod['_id']}", use_container_width=True):
                            update_data = {
                                "nombre": nuevo_nombre, "tipo": nuevo_tipo, "precio": np, "stock": ns, "precio_detalle": ndp, "stock_detalle": nds, "detalle": ndtxt,
                                "fecha_lanzamiento": fecha_final_ed
                            }
                            if nuevo_tipo in tipos_con_atributo:
                                update_data["atributo"] = nuevo_atributo
                                if nuevo_atributo_2 != "Ninguno": update_data["atributo_2"] = nuevo_atributo_2
                                else: update_data["atributo_2"] = "Ninguno"
                            col_productos.update_one({"_id": ObjectId(prod["_id"])}, {"$set": update_data})
                            forzar_actualizacion()
                            st.rerun()
                            
                        if c_bd.button("🗑️ Eliminar Definitivo", key=f"del_{prod['_id']}", use_container_width=True):
                            col_productos.delete_one({"_id": ObjectId(prod["_id"])})
                            forzar_actualizacion()
                            st.rerun()

        # --- RENDERIZADO NORMAL DE TARJETAS (PÚBLICO, CATÁLOGO Y AGOTADOS) ---
        else:
            cols = st.columns(3)
            for index, prod in enumerate(productos_a_mostrar):
                info_img = obtener_foto_mongo(str(prod["_id"]))
                
                with cols[index % 3]:
                    st.markdown(f"<h4 style='margin-bottom: 5px; margin-top: 0px; font-size: 20px;'>{prod['nombre']}</h4>", unsafe_allow_html=True)
                    
                    if tipo_busqueda == "Piezas / Detalles 🛠️":
                        imagenes_del_producto = info_img.get("imagenes_detalle_b64", info_img.get("imagenes_b64", []))
                    else:
                        imagenes_del_producto = info_img.get("imagenes_b64", [])
                        if not imagenes_del_producto: imagenes_del_producto = info_img.get("imagenes_detalle_b64", [])
                            
                    if not imagenes_del_producto and "imagen_b64" in info_img: 
                        imagenes_del_producto = [info_img["imagen_b64"]]
                    
                    if imagenes_del_producto:
                        html_galeria = '<div class="galeria-container">'
                        for b64_img in imagenes_del_producto: html_galeria += f'<img src="data:image/jpeg;base64,{b64_img}" class="galeria-img">'
                        html_galeria += '</div>'
                        st.markdown(html_galeria, unsafe_allow_html=True)
                        if len(imagenes_del_producto) > 1: st.markdown("<p style='text-align: center; color: #aaa; font-size: 13px; margin-top: -5px; margin-bottom: 5px;'>👉 Desliza la foto</p>", unsafe_allow_html=True)
                        if st.button("🔍 Ampliar foto", key=f"zoom_{prod['_id']}", use_container_width=True): abrir_zoom(prod['nombre'], imagenes_del_producto)
                    
                    stock_normal = prod.get('stock', 0)
                    precio_normal = prod.get('precio', 0.0)
                    stock_detalle = prod.get('stock_detalle', 0)
                    precio_detalle = prod.get('precio_detalle', 0.0)
                    texto_detalle = prod.get('detalle', "")

                    if texto_detalle and 'stock_detalle' not in prod:
                        stock_detalle, precio_detalle = stock_normal, precio_normal
                        stock_normal, precio_normal = 0, 0.0
                    
                    tipo_real = prod.get("tipo", "Bakugan")
                    if tipo_real == "Bakugan" or "atributo" in prod: 
                        attr1 = prod.get('atributo', 'N/A')
                        attr2 = prod.get('atributo_2', 'Ninguno')
                        if attr2 != "Ninguno":
                            st.markdown(f"<div style='margin-top: 5px; margin-bottom: -10px;'><b>Atributos:</b> {attr1} / {attr2}</div>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"<div style='margin-top: 5px; margin-bottom: -10px;'><b>Atributo:</b> {attr1}</div>", unsafe_allow_html=True)
                            
                    elif tipo_real == "Carta": st.markdown(f"<div style='margin-top: 5px; margin-bottom: -10px;'><b>Material:</b> {prod.get('material', 'N/A')}</div>", unsafe_allow_html=True)
                    elif tipo_real == "BakuCore": st.markdown(f"<div style='margin-top: 5px; margin-bottom: -10px;'><b>Símbolo:</b> {prod.get('simbolo', 'N/A')}</div>", unsafe_allow_html=True)
                    
                    if not es_modo_edicion:
                        en_carrito_normal = sum(1 for item in st.session_state.carrito if item["_id"] == prod["_id"] and item.get("variante") == "normal")
                        en_carrito_detalle = sum(1 for item in st.session_state.carrito if item["_id"] == prod["_id"] and item.get("variante") == "detalle")
                        
                        if stock_normal > 0:
                            cu_norm = " c/u" if stock_normal > 1 else ""
                            st.write(f"🟢 **Perfecta:** ${precio_normal:,.2f}{cu_norm} (Disp: {stock_normal})")
                            
                            if en_carrito_normal == 0:
                                if st.button("🛒 Añadir", key=f"add_n_{prod['_id']}", use_container_width=True):
                                    st.session_state.carrito.append({"_id": prod["_id"], "nombre": f"{prod['nombre']}", "precio": precio_normal, "variante": "normal", "tipo": tipo_real})
                                    guardar_carrito() 
                                    
                                    if promo_seleccionada == "🌟 Súper 3x2" and tipo_real not in ["Carta", "BakuCore", "Extra"]:
                                        eleg = [i for i in st.session_state.carrito if i.get("tipo") not in ["Carta", "BakuCore", "Extra"] and i.get("variante") != "detalle"]
                                        if len(eleg) % 3 == 2: st.session_state.abrir_modal_3x2 = True
                                            
                                    st.rerun()
                            else: 
                                st.button("✅ En carrito", disabled=True, key=f"max_n_{prod['_id']}", use_container_width=True)
                            
                        if stock_detalle > 0:
                            st.markdown(f"<span style='color:#f39c12; font-size: 0.9em;'>⚠️ **Detalle:** {texto_detalle}</span>", unsafe_allow_html=True)
                            cu_det = " c/u" if stock_detalle > 1 else ""
                            st.write(f"🟠 **C/Detalle:** ${precio_detalle:,.2f}{cu_det} (Disp: {stock_detalle})")
                            
                            if en_carrito_detalle == 0:
                                if st.button("🛒 Añadir", key=f"add_d_{prod['_id']}", use_container_width=True):
                                    st.session_state.carrito.append({"_id": prod["_id"], "nombre": f"{prod['nombre']} (Detalle)", "precio": precio_detalle, "variante": "detalle", "tipo": tipo_real})
                                    guardar_carrito() 
                                    st.rerun()
                        else: 
                            st.button("✅ En carrito", disabled=True, key=f"max_d_{prod['_id']}", use_container_width=True)

                    if es_modo_edicion:
                        st.markdown('<hr style="margin: 10px 0px; border: none; border-top: 1px solid rgba(255,255,255,0.2);">', unsafe_allow_html=True)
                        
                        titulo_expander = "✏️ Editar"
                        if es_modo_admin_agotados: titulo_expander = "✏️ Editar / Restock"
                        
                        with st.expander(titulo_expander):
                            nuevo_nombre = st.text_input("Nombre del Producto", value=prod['nombre'], key=f"enom_{prod['_id']}")
                            
                            idx_tipo = tipos_producto.index(tipo_real) if tipo_real in tipos_producto else 0
                            nuevo_tipo = st.selectbox("Categoría / Tipo", tipos_producto, index=idx_tipo, key=f"etipo_{prod['_id']}")

                            attr_actual = prod.get('atributo', categorias[1]) 
                            try:
                                idx_attr = categorias[1:].index(attr_actual)
                            except ValueError:
                                idx_attr = 0
                                
                            attr2_actual = prod.get('atributo_2', "Ninguno") 
                            try:
                                idx_attr2 = (["Ninguno"] + categorias[1:]).index(attr2_actual)
                            except ValueError:
                                idx_attr2 = 0

                            c_a1, c_a2 = st.columns(2)
                            with c_a1: nuevo_atributo = st.selectbox("Atributo", categorias[1:], index=idx_attr, key=f"eattr_{prod['_id']}")
                            with c_a2: nuevo_atributo_2 = st.selectbox("Atributo 2 (Fusión)", ["Ninguno"] + categorias[1:], index=idx_attr2, key=f"eattr2_{prod['_id']}")

                            np = st.number_input("Precio N.", value=float(precio_normal), step=10.0, key=f"epn_{prod['_id']}")
                            ns = st.number_input("Stock N.", value=int(stock_normal), step=1, key=f"esn_{prod['_id']}")
                            ndp = st.number_input("Precio D.", value=float(precio_detalle), step=10.0, key=f"epd_{prod['_id']}")
                            nds = st.number_input("Stock D.", value=int(stock_detalle), step=1, key=f"esd_{prod['_id']}")
                            ndtxt = st.text_input("Detalle", value=texto_detalle, key=f"etxt_{prod['_id']}")
                            
                            es_prog_ed = st.checkbox("⏳ Programar lanzamiento", value=False, key=f"prog_{prod['_id']}")
                            fecha_final_ed = None
                            if es_prog_ed:
                                c_f, c_h = st.columns(2)
                                f_ed = c_f.date_input("Fecha", value=hora_qro().date(), key=f"fed_{prod['_id']}")
                                h_ed = c_h.time_input("Hora", value=hora_qro().time(), key=f"hed_{prod['_id']}")
                                fecha_final_ed = datetime.combine(f_ed, h_ed)
                            
                            if st.button("💾 Guardar", key=f"save_{prod['_id']}", use_container_width=True):
                                update_data = {
                                    "nombre": nuevo_nombre, "tipo": nuevo_tipo, "precio": np, "stock": ns, "precio_detalle": ndp, "stock_detalle": nds, "detalle": ndtxt,
                                    "fecha_lanzamiento": fecha_final_ed
                                }
                                
                                if nuevo_tipo in tipos_con_atributo:
                                    update_data["atributo"] = nuevo_atributo
                                    if nuevo_atributo_2 != "Ninguno":
                                        update_data["atributo_2"] = nuevo_atributo_2
                                    else:
                                        update_data["atributo_2"] = "Ninguno"
                                        
                                col_productos.update_one({"_id": ObjectId(prod["_id"])}, {"$set": update_data})
                                forzar_actualizacion()
                                st.rerun()
                                
                        if st.button("🗑️ Eliminar Definitivo", key=f"del_{prod['_id']}", use_container_width=True):
                            col_productos.delete_one({"_id": ObjectId(prod["_id"])})
                            forzar_actualizacion()
                            st.rerun()
                            
    if len(productos_filtrados) > st.session_state.limite_items:
        st.markdown("---")
        if st.button("⬇️ Cargar más piezas", use_container_width=True, type="primary"):
            st.session_state.limite_items += 12
            st.rerun()