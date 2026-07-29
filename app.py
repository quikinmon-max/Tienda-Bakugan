import streamlit as st
import pymongo
import base64
import random
import uuid
import urllib.parse
from datetime import datetime, timedelta
from PIL import Image, ImageOps
import io

# ---------------- CONFIGURACIÓN DE PÁGINA ----------------
st.set_page_config(
    page_title="Bakugan Market", 
    page_icon="🔥", 
    layout="wide"
)

# ---------------- INICIALIZAR MEMORIA Y SEMILLA ALEATORIA ----------------
if 'carrito' not in st.session_state:
    st.session_state.carrito = []

if 'rand_seed' not in st.session_state:
    st.session_state.rand_seed = random.randint(1, 999999)

# ---------------- CONEXIÓN A MONGODB ----------------
@st.cache_resource
def init_connection():
    MONGO_URI = st.secrets["MONGO_URI"] 
    client = pymongo.MongoClient(MONGO_URI)
    return client

client = init_connection()
db = client["bakugan_market"]
col_productos = db["productos"]
col_apartados = db["apartados"]
col_config = db["configuracion"] 
col_ventas = db["ventas"] 
col_carritos = db["carritos_temporales"] 

# --- MIGRACIÓN AUTOMÁTICA DE APARTADOS VIEJOS ---
# Actualiza los apartados que se hicieron antes de esta mejora para que tengan vencimiento
viejos = col_apartados.find({"fecha_vencimiento": {"$exists": False}})
for v in viejos:
    fv = v.get("fecha_apartado", datetime.now()) + timedelta(days=3)
    col_apartados.update_one({"_id": v["_id"]}, {"$set": {"fecha_vencimiento": fv, "anticipo": 0.0}})

# ---------------- SISTEMA ANTICAÍDAS (CARRITO Y SESIÓN) ----------------
if 'session_id' not in st.session_state:
    if "sesion" in st.query_params:
        st.session_state.session_id = st.query_params["sesion"]
    else:
        st.session_state.session_id = str(uuid.uuid4())[:8] 
        st.query_params["sesion"] = st.session_state.session_id

if 'carrito' not in st.session_state or not st.session_state.carrito:
    carrito_guardado = col_carritos.find_one({"_id": st.session_state.session_id})
    if carrito_guardado:
        st.session_state.carrito = carrito_guardado.get("items", [])
    else:
        st.session_state.carrito = []

def guardar_carrito():
    col_carritos.update_one(
        {"_id": st.session_state.session_id},
        {"$set": {"items": st.session_state.carrito, "fecha": datetime.now()}},
        upsert=True
    )

# Memoria para que no te saque del modo Admin si la página se reinicia
if 'admin_autenticado' not in st.session_state:
    st.session_state.admin_autenticado = False

# ---------------- MOTOR DE COMPRESIÓN DE IMÁGENES ----------------
def comprimir_imagen(img_file):
    img = Image.open(img_file)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
    img.thumbnail((800, 800))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=70)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

# ---------------- FUNCIÓN DE AMPLIACIÓN DE FOTOS (MODAL) ----------------
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

# ---------------- CARGAR DISEÑO PERSONALIZADO (FONDO Y CSS) ----------------
config_data = col_config.find_one({"_id": "sitio_prefs"})
fondo_b64 = config_data.get("fondo_b64") if config_data else None
logo_b64 = config_data.get("logo_b64") if config_data else None

css_global = f"""
<style>
.stApp {{
    {'background-image: url("data:image/png;base64,' + fondo_b64 + '");' if fondo_b64 else ''}
    background-size: cover; background-position: center; background-repeat: no-repeat; background-attachment: fixed;
}}
.stApp > header {{ background-color: transparent; }}
.block-container {{
    background-color: rgba(14, 17, 23, 0.85); 
    padding-top: 5rem !important; padding-right: 2rem; padding-bottom: 2rem; padding-left: 2rem;
    margin-top: 2rem; border-radius: 15px;
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
    .block-container {{ padding-top: 3rem !important; margin-top: 0rem; }}
    .stTextInput input {{ font-size: 16px !important; padding: 0.6rem !important; }}
    .stButton > button {{ font-size: 16px !important; padding: 0.5rem 1rem !important; min-height: 2.8rem !important; }}
    div[data-testid="stPopover"] > button {{ font-size: 16px !important; padding: 0.6rem 1rem !important; min-height: 2.8rem !important; }}
}}
</style>
"""
st.markdown(css_global, unsafe_allow_html=True)

# ---------------- MANTENIMIENTO INTELIGENTE (AHORA USA FECHA DE VENCIMIENTO) ----------------
def mantenimiento_base_datos():
    ahora = datetime.now()
    # Eliminar solo los que ya pasaron de su fecha_vencimiento
    vencidos = col_apartados.find({"fecha_vencimiento": {"$lt": ahora}})
    for doc in vencidos:
        campo = doc.get("campo_stock", "stock")
        col_productos.update_one({"_id": doc["producto_id"]}, {"$inc": {campo: 1}})
        col_apartados.delete_one({"_id": doc["_id"]})
    
    limite_cart = datetime.now() - timedelta(days=1)
    col_carritos.delete_many({"fecha": {"$lt": limite_cart}})

mantenimiento_base_datos()

# ---------------- VARIABLES GLOBALES ----------------
categorias = ["Todos", "Pyrus 🔥", "Aquos 💧", "Ventus 🍃", "Darkus 🌑", "Haos ✨", "Subterra 🪨"]
materiales = ["Todas", "Metálica", "Cartón"]
simbolos_core = ["Todos", "Fist ✊", "Flaming Fist 🔥✊", "Shield 🛡️", "Magic Shield ✨🛡️", "Helix 🧬"]

# =====================================================================
# =========================== MENÚ LATERAL ============================
# =====================================================================

if logo_b64:
    st.sidebar.markdown(f'<style>.logo-celular {{ width: 100%; border-radius: 8px; margin-bottom: 10px; }} @media (max-width: 768px) {{ .logo-celular {{ width: 45%; margin-left: auto; margin-right: auto; display: block; }} }} </style> <img src="data:image/png;base64,{logo_b64}" class="logo-celular">', unsafe_allow_html=True)
else:
    st.sidebar.markdown("### 🛒 Mi Tienda")

st.sidebar.header("Filtros Avanzados")

tipo_busqueda = st.sidebar.selectbox("¿Qué buscas?", [
    "Todo el Catálogo 🌍", "Bakugans 🔥", "Cartas 🃏", "BakuCores 🛑", "Vehículos 🏎️", "Armamentos ⚔️", "BakuTech 🦾", "Extras 🎁", "Sets de Batalla 🏟️", "Deka 🌐", "Piezas / Detalles 🛠️"
])

if tipo_busqueda == "Bakugans 🔥": sub_filtro = st.sidebar.selectbox("Filtra por Atributo", categorias)
elif tipo_busqueda == "Cartas 🃏": sub_filtro = st.sidebar.selectbox("Filtra por Material", materiales)
elif tipo_busqueda == "BakuCores 🛑": sub_filtro = st.sidebar.selectbox("Filtra por Símbolo", simbolos_core)
else: sub_filtro = "Todos"

es_admin_url = st.query_params.get("jefe") == "1"
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
        vista_admin = st.sidebar.radio("Opciones de Administrador", ["Ver Catálogo", "➕ Agregar Producto", "📋 Ver Apartados", "📊 Finanzas y Ventas", "🎨 Personalizar Página"])

st.sidebar.markdown("<div style='height: 400px;'></div>", unsafe_allow_html=True)

# =====================================================================
# ======================== PANTALLA PRINCIPAL =========================
# =====================================================================

if vista_admin == "📊 Finanzas y Ventas":
    st.title("📊 Panel de Analítica Financiera")
    ventas = list(col_ventas.find({}))
    if not ventas:
        st.info("Aún no tienes ventas registradas para analizar.")
    else:
        hoy = datetime.now()
        def filtrar_por_fecha(dias):
            return [v for v in ventas if v["fecha_venta"] >= hoy - timedelta(days=dias)]
        ventas_hoy = [v for v in ventas if v["fecha_venta"].date() == hoy.date()]
        ventas_semana, ventas_mes, ventas_anio = filtrar_por_fecha(7), filtrar_por_fecha(30), filtrar_por_fecha(365)
        
        def calcular_metricas(lista_ventas):
            ingresos = sum(v.get("precio_total", 0) for v in lista_ventas)
            gastos = sum(v.get("gasto_envio", 0) for v in lista_ventas)
            return ingresos, gastos, ingresos - gastos
            
        tab1, tab2, tab3, tab4 = st.tabs(["Hoy", "Últimos 7 Días", "Últimos 30 Días", "Este Año"])
        for tab, datos_rango in [(tab1, ventas_hoy), (tab2, ventas_semana), (tab3, ventas_mes), (tab4, ventas_anio)]:
            with tab:
                ing, gas, gan = calcular_metricas(datos_rango)
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("📦 Vendidas", len(datos_rango))
                col2.metric("💸 Brutos", f"${ing:,.2f}")
                col3.metric("📉 Gastos", f"${gas:,.2f}")
                col4.metric("💰 Neta", f"${gan:,.2f}")
                
        st.markdown("---")
        st.subheader("📝 Historial Detallado de Ventas")
        for v in reversed(ventas):
            neta, cobro_envio, gasto_envio = v.get('precio_total', 0) - v.get('gasto_envio', 0), v.get('ingreso_envio', 0), v.get('gasto_envio', 0)
            fecha_str, obs = v['fecha_venta'].strftime('%d/%m/%Y'), v.get('observaciones', 'Ninguna')
            st.markdown(f'<div class="tarjeta-cliente"><div style="font-size: 14px; margin-bottom: 5px;"><span style="color: #aaa;">📅 {fecha_str}</span> &nbsp;|&nbsp; 👤 <b>{v["cliente"]}</b></div><div style="font-size: 15px; margin-bottom: 5px;">💰 <b>Ganancia Neta: <span style="color: #2ecc71;">${neta:,.2f}</span></b> &nbsp;|&nbsp; 📦 Cobro Envío: <span style="color: #f1c40f;">${cobro_envio:,.2f}</span> &nbsp;|&nbsp; 📉 Costo Guía: <span style="color: #e74c3c;">${gasto_envio:,.2f}</span></div><div style="font-size: 13px; color: #ccc;">📝 <i>Obs: {obs}</i></div></div>', unsafe_allow_html=True)

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
                st.success("¡Diseño actualizado! Recarga la página.")
                st.rerun()

elif vista_admin == "➕ Agregar Producto":
    st.title("🛠️ Agregar nuevo producto")
    
    tipo_prod = st.selectbox("Tipo de Producto", [
        "Bakugan", "Carta", "BakuCore", "Vehículo", "Armamento", "BakuTech", "Extra", "Set de Batalla", "Deka"
    ])
    
    nombre = st.text_input("Nombre / Descripción principal")
    
    col1, col2, col3 = st.columns(3)
    with col1: atributo_form = st.selectbox("Atributo", categorias[1:], disabled=(tipo_prod != "Bakugan")) 
    with col2: material_form = st.selectbox("Material", materiales[1:], disabled=(tipo_prod != "Carta"))
    with col3: simbolo_form = st.selectbox("Símbolo", simbolos_core[1:], disabled=(tipo_prod != "BakuCore"))
    
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
    
    if st.button("Subir Producto al Catálogo"):
        if nombre and (imagenes_subidas or imagenes_detalle_subidas) and (precio > 0 or precio_detalle > 0):
            lista_imagenes_b64 = [comprimir_imagen(img) for img in imagenes_subidas[:6]] if imagenes_subidas else []
            lista_imagenes_detalle_b64 = [comprimir_imagen(img) for img in imagenes_detalle_subidas[:6]] if imagenes_detalle_subidas else []
            
            if con_detalle and not lista_imagenes_detalle_b64:
                lista_imagenes_detalle_b64 = lista_imagenes_b64
                
            nuevo_prod = {
                "tipo": tipo_prod, "nombre": nombre, "precio": precio, "stock": stock,
                "precio_detalle": precio_detalle, "stock_detalle": stock_detalle, "detalle": detalle_prod,
                "imagenes_b64": lista_imagenes_b64, "imagenes_detalle_b64": lista_imagenes_detalle_b64
            }
            if tipo_prod == "Bakugan": nuevo_prod["atributo"] = atributo_form
            elif tipo_prod == "Carta": nuevo_prod["material"] = material_form
            elif tipo_prod == "BakuCore": nuevo_prod["simbolo"] = simbolo_form
                
            col_productos.insert_one(nuevo_prod)
            st.success(f"¡{nombre} subido con éxito!")
            st.rerun() 
        else:
            st.error("Falta el nombre, subir foto o asignar precio.")

elif vista_admin == "📋 Ver Apartados":
    st.title("📋 Registro de Clientes y Apartados")
    st.markdown("---")
    todos_los_apartados = list(col_apartados.find({}))
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
            
            total_cliente = 0
            total_anticipo = 0
            fechas_venc = []
            nombres_items = []
            
            for item in items:
                fecha_str = item["fecha_apartado"].strftime("%d/%m")
                precio_item = item.get("precio", 0.0)
                total_cliente += precio_item
                total_anticipo += item.get("anticipo", 0.0)
                fechas_venc.append(item.get("fecha_vencimiento", datetime.now()))
                nombres_items.append(item['nombre_producto'])
                st.write(f"- **{item['nombre_producto']}** (${precio_item}) _[Apt: {fecha_str}]_")
            
            fecha_max_venc = max(fechas_venc).strftime("%d/%m %H:%M")
            restante = total_cliente - total_anticipo
            
            st.markdown(f"**⏳ Vence el:** {fecha_max_venc}")
            st.markdown(f"**💰 Total pedido:** ${total_cliente}")
            if total_anticipo > 0:
                st.markdown(f"**💸 Anticipo dado:** <span style='color:#f39c12;'>${total_anticipo}</span>", unsafe_allow_html=True)
                st.markdown(f"**⚠️ Restante a cobrar:** <span style='color:#e74c3c; font-size:1.2em; font-weight:bold;'>${restante}</span>", unsafe_allow_html=True)
            else:
                st.markdown(f"**⚠️ Total a cobrar:** <span style='color:#2ecc71; font-size:1.2em; font-weight:bold;'>${total_cliente}</span>", unsafe_allow_html=True)
            
            col_conf, col_pro, col_canc = st.columns(3)
            with col_conf:
                with st.expander("✅ Procesar Venta"):
                    cobro_envio = st.number_input("Cobro Envío $", min_value=0.0, step=10.0, key=f"cobro_{tel}")
                    gastos = st.number_input("Costo Guía $", min_value=0.0, step=10.0, key=f"gasto_{tel}")
                    obs = st.text_input("Obs", key=f"obs_{tel}")
                    if st.button("Confirmar", key=f"btn_venta_{tel}"):
                        col_ventas.insert_one({
                            "cliente": nombre_cliente, "telefono": tel, "productos": nombres_items,
                            "precio_productos": total_cliente, "ingreso_envio": cobro_envio,
                            "anticipo_previo": total_anticipo,
                            "precio_total": total_cliente + cobro_envio, "gasto_envio": gastos,
                            "observaciones": obs, "fecha_venta": datetime.now()
                        })
                        for item in items: col_apartados.delete_one({"_id": item["_id"]})
                        st.success("¡Venta registrada!")
                        st.rerun()
                        
            with col_pro:
                with st.expander("⏳ Prórroga / Abono"):
                    nuevo_anticipo = st.number_input("Abonar Anticipo $", min_value=0.0, step=50.0, key=f"ant_{tel}")
                    dias_pro = st.number_input("Sumar Días Extra", min_value=0, step=1, value=1, key=f"dias_{tel}")
                    if st.button("Aplicar", key=f"btn_pro_{tel}"):
                        ids_items = [item["_id"] for item in items]
                        # Abonamos el anticipo al primer item para no duplicar sumas
                        if nuevo_anticipo > 0:
                            col_apartados.update_one({"_id": ids_items[0]}, {"$inc": {"anticipo": nuevo_anticipo}})
                        # Actualizamos la fecha de vencimiento a todos los items del cliente
                        if dias_pro > 0:
                            nueva_fecha = max(fechas_venc) + timedelta(days=dias_pro)
                            col_apartados.update_many({"_id": {"$in": ids_items}}, {"$set": {"fecha_vencimiento": nueva_fecha}})
                        st.success("¡Prórroga aplicada!")
                        st.rerun()
                        
            with col_canc:
                with st.expander("🚫 Cancelar"):
                    if st.button("Confirmar", key=f"btn_cancel_{tel}"):
                        for doc in items:
                            campo = doc.get("campo_stock", "stock")
                            col_productos.update_one({"_id": doc["producto_id"]}, {"$inc": {campo: 1}})
                            col_apartados.delete_one({"_id": doc["_id"]})
                        st.success("¡Cancelado!")
                        st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

else:
    # --- VISTA DEL CATÁLOGO ---
    es_modo_admin_catalogo = st.session_state.admin_autenticado and vista_admin == "Ver Catálogo"
    
    if es_modo_admin_catalogo:
        st.title("🛠️ Administrar Catálogo e Inventario")
        busqueda_texto = st.text_input("🔍 Buscar pieza por nombre...")
    else:
        col_tit, col_busc, col_cart = st.columns([1.5, 2, 1.5])
        with col_tit: st.markdown("### 🔥 Catálogo Libre")
        with col_busc: busqueda_texto = st.text_input("Buscar", placeholder="🔍 Buscar...", label_visibility="collapsed")
        with col_cart:
            cantidad_carrito = len(st.session_state.carrito)
            total_carrito = sum(item['precio'] for item in st.session_state.carrito)
            with st.popover(f"🛒 Carrito ({cantidad_carrito}) - ${total_carrito}", use_container_width=True):
                if 'wa_link' in st.session_state:
                    st.success("✅ ¡Piezas apartadas!")
                    st.markdown(f"[**📲 HAZ CLIC AQUÍ PARA AVISARME POR WHATSAPP**]({st.session_state.wa_link})")
                    if st.button("Cerrar Aviso", use_container_width=True):
                        del st.session_state['wa_link']
                        st.rerun()
                st.markdown("#### Resumen:")
                if cantidad_carrito > 0:
                    for i, item in enumerate(st.session_state.carrito):
                        c1, c2 = st.columns([4, 1])
                        c1.markdown(f"<span style='font-size:0.9em;'>{item['nombre']} - **${item['precio']}**</span>", unsafe_allow_html=True)
                        if c2.button("❌", key=f"del_cart_{i}_{item['_id']}"):
                            st.session_state.carrito.pop(i)
                            guardar_carrito() 
                            st.rerun()
                    st.markdown("---")
                    st.markdown(f"**Total a pagar: ${total_carrito}**")
                    nom = st.text_input("Tu Nombre", key="checkout_nom")
                    tel = st.text_input("Tu WhatsApp", key="checkout_tel")
                    
                    if st.button("Confirmar Apartado", use_container_width=True, type="primary"):
                        if nom and tel:
                            # 1. Guardar en Base de Datos de apartados CON FECHA DE VENCIMIENTO (+3 días inicial)
                            for prod_cart in st.session_state.carrito:
                                db_prod = col_productos.find_one({"_id": prod_cart["_id"]})
                                campo_stock = "stock"
                                if prod_cart.get("variante") == "detalle":
                                    campo_stock = "stock_detalle" if "stock_detalle" in db_prod else "stock"
                                    
                                col_apartados.insert_one({
                                    "producto_id": prod_cart["_id"], "nombre_producto": prod_cart["nombre"],
                                    "precio": prod_cart["precio"], "comprador_nombre": nom, "comprador_telefono": tel,
                                    "fecha_apartado": datetime.now(), 
                                    "fecha_vencimiento": datetime.now() + timedelta(days=3), # <-- NUEVA LÓGICA DE VENCIMIENTO
                                    "campo_stock": campo_stock,
                                    "anticipo": 0.0 # <-- NUEVO CAMPO DE ANTICIPO INICIAL
                                })
                                col_productos.update_one({"_id": prod_cart["_id"]}, {"$inc": {campo_stock: -1}})
                            
                            # 2. CONSTRUIR EL MENSAJE DETALLADO DE WHATSAPP
                            texto_crudo = f"Hola, soy {nom}. Acabo de apartar {cantidad_carrito} piezas por un total de ${total_carrito}.\n\nMis piezas son:\n"
                            for item in st.session_state.carrito:
                                texto_crudo += f"👉 {item['nombre']} (${item['precio']})\n"
                            
                            texto_url = urllib.parse.quote(texto_crudo)
                            st.session_state.wa_link = f"https://wa.me/4462879839?text={texto_url}"
                            
                            # 3. Vaciar carrito
                            st.session_state.carrito = [] 
                            guardar_carrito()
                            st.rerun()
                        else: st.warning("⚠️ Faltan datos.")
                else: st.info("Carrito vacío.")

    st.markdown("---")

    query_base = {}
    if busqueda_texto: query_base["nombre"] = {"$regex": busqueda_texto, "$options": "i"}

    if tipo_busqueda == "Bakugans 🔥":
        query_base["$or"] = [{"tipo": "Bakugan"}, {"tipo": {"$exists": False}}]
        if sub_filtro != "Todos": query_base["atributo"] = sub_filtro
    elif tipo_busqueda == "Cartas 🃏":
        query_base["tipo"] = "Carta"
        if sub_filtro != "Todas": query_base["material"] = sub_filtro
    elif tipo_busqueda == "BakuCores 🛑": 
        query_base["tipo"] = "BakuCore"
        if sub_filtro != "Todos": query_base["simbolo"] = sub_filtro
    elif tipo_busqueda == "Vehículos 🏎️": query_base["tipo"] = "Vehículo"
    elif tipo_busqueda == "Armamentos ⚔️": query_base["tipo"] = "Armamento"
    elif tipo_busqueda == "BakuTech 🦾": query_base["tipo"] = "BakuTech"
    elif tipo_busqueda == "Extras 🎁": query_base["tipo"] = "Extra"
    elif tipo_busqueda == "Sets de Batalla 🏟️": query_base["tipo"] = "Set de Batalla"
    elif tipo_busqueda == "Deka 🌐": query_base["tipo"] = "Deka"

    productos_crudos = list(col_productos.find(query_base))
    productos_filtrados = []

    for prod in productos_crudos:
        stock_normal = prod.get('stock', 0)
        stock_detalle = prod.get('stock_detalle', 0)
        texto_detalle = prod.get('detalle', "")
        
        if texto_detalle and 'stock_detalle' not in prod:
            stock_detalle = stock_normal
            stock_normal = 0
            
        if es_modo_admin_catalogo:
            if tipo_busqueda == "Piezas / Detalles 🛠️" and not texto_detalle: continue
            if tipo_busqueda != "Piezas / Detalles 🛠️" and tipo_busqueda != "Todo el Catálogo 🌍" and texto_detalle and stock_normal == 0 and stock_detalle > 0: continue
            productos_filtrados.append(prod)
        else:
            if tipo_busqueda == "Piezas / Detalles 🛠️":
                if texto_detalle and stock_detalle > 0: productos_filtrados.append(prod)
            elif tipo_busqueda == "Todo el Catálogo 🌍":
                if stock_normal > 0 or stock_detalle > 0: productos_filtrados.append(prod)
            else:
                if stock_normal > 0: productos_filtrados.append(prod)

    # ---------------- APLICAR ALEATORIEDAD CON SEMILLA ----------------
    rng = random.Random(st.session_state.rand_seed)
    rng.shuffle(productos_filtrados)

    if not productos_filtrados:
        st.info("No encontramos piezas en esta categoría.")
    else:
        cols = st.columns(3)
        for index, prod in enumerate(productos_filtrados):
            with cols[index % 3]:
                st.markdown(f"### {prod['nombre']}")
                
                if tipo_busqueda == "Piezas / Detalles 🛠️":
                    imagenes_del_producto = prod.get("imagenes_detalle_b64", prod.get("imagenes_b64", []))
                else:
                    imagenes_del_producto = prod.get("imagenes_b64", [])
                    if not imagenes_del_producto:
                        imagenes_del_producto = prod.get("imagenes_detalle_b64", [])
                        
                if not imagenes_del_producto and "imagen_b64" in prod: 
                    imagenes_del_producto = [prod["imagen_b64"]]
                
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
                    stock_detalle = stock_normal
                    precio_detalle = precio_normal
                    stock_normal = 0
                    precio_normal = 0.0
                
                tipo_real = prod.get("tipo", "Bakugan")
                if tipo_real == "Bakugan" or "atributo" in prod: st.write(f"**Atributo:** {prod.get('atributo', 'N/A')}")
                elif tipo_real == "Carta": st.write(f"**Material:** {prod.get('material', 'N/A')}")
                elif tipo_real == "BakuCore": st.write(f"**Símbolo:** {prod.get('simbolo', 'N/A')}")
                
                if not es_modo_admin_catalogo:
                    en_carrito_normal = sum(1 for item in st.session_state.carrito if item["_id"] == prod["_id"] and item.get("variante") == "normal")
                    en_carrito_detalle = sum(1 for item in st.session_state.carrito if item["_id"] == prod["_id"] and item.get("variante") == "detalle")
                    
                    if stock_normal == 0 and stock_detalle == 0:
                        st.markdown("🚨 **AGOTADO**", unsafe_allow_html=True)
                    else:
                        if stock_normal > 0:
                            cu_norm = " c/u" if stock_normal > 1 else ""
                            st.write(f"🟢 **Perfecta:** ${precio_normal}{cu_norm} (Disp: {stock_normal})")
                            
                            if (stock_normal - en_carrito_normal) > 0:
                                if st.button(f"🛒 Añadir Normal", key=f"add_n_{prod['_id']}", use_container_width=True):
                                    st.session_state.carrito.append({"_id": prod["_id"], "nombre": f"{prod['nombre']}", "precio": precio_normal, "variante": "normal"})
                                    guardar_carrito() 
                                    st.rerun()
                            else: st.button("✅ En carrito (Máx)", disabled=True, key=f"max_n_{prod['_id']}", use_container_width=True)
                            
                        if stock_detalle > 0:
                            st.markdown(f"<span style='color:#f39c12; font-size: 0.9em;'>⚠️ **Detalle:** {texto_detalle}</span>", unsafe_allow_html=True)
                            
                            cu_det = " c/u" if stock_detalle > 1 else ""
                            st.write(f"🟠 **C/Detalle:** ${precio_detalle}{cu_det} (Disp: {stock_detalle})")
                            
                            if (stock_detalle - en_carrito_detalle) > 0:
                                if st.button(f"🛒 Añadir c/Detalle", key=f"add_d_{prod['_id']}", use_container_width=True):
                                    st.session_state.carrito.append({"_id": prod["_id"], "nombre": f"{prod['nombre']} (Detalle)", "precio": precio_detalle, "variante": "detalle"})
                                    guardar_carrito() 
                                    st.rerun()
                            else: st.button("✅ Detalle en carrito", disabled=True, key=f"max_d_{prod['_id']}", use_container_width=True)

                if es_modo_admin_catalogo:
                    st.markdown("---")
                    with st.expander("✏️ Editar"):
                        np = st.number_input("Precio N.", value=float(precio_normal), step=10.0, key=f"epn_{prod['_id']}")
                        ns = st.number_input("Stock N.", value=int(stock_normal), step=1, key=f"esn_{prod['_id']}")
                        ndp = st.number_input("Precio D.", value=float(precio_detalle), step=10.0, key=f"epd_{prod['_id']}")
                        nds = st.number_input("Stock D.", value=int(stock_detalle), step=1, key=f"esd_{prod['_id']}")
                        ndtxt = st.text_input("Detalle", value=texto_detalle, key=f"etxt_{prod['_id']}")
                        
                        if st.button("💾 Guardar", key=f"save_{prod['_id']}", use_container_width=True):
                            col_productos.update_one({"_id": prod["_id"]}, {"$set": {
                                "precio": np, "stock": ns, "precio_detalle": ndp, "stock_detalle": nds, "detalle": ndtxt
                            }})
                            st.rerun()
                            
                    if st.button("🗑️ Eliminar", key=f"del_{prod['_id']}", use_container_width=True):
                        col_productos.delete_one({"_id": prod["_id"]})
                        st.rerun()