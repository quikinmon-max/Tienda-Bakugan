import streamlit as st
import pymongo
import base64
from datetime import datetime, timedelta
from PIL import Image, ImageOps
import io

# ---------------- CONFIGURACIÓN DE PÁGINA ----------------
st.set_page_config(
    page_title="Bakugan Market", 
    page_icon="🔥", 
    layout="wide"
)

# ---------------- INICIALIZAR CARRITO EN MEMORIA ----------------
if 'carrito' not in st.session_state:
    st.session_state.carrito = []

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

# ---------------- MOTOR DE COMPRESIÓN DE IMÁGENES ----------------
def comprimir_imagen(img_file):
    img = Image.open(img_file)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
    img.thumbnail((800, 800))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=70)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

# ---------------- FUNCIÓN DE AMPLIACIÓN DE FOTOS (MODAL CON CARRETE) ----------------
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
    background-size: cover;
    background-position: center;
    background-repeat: no-repeat;
    background-attachment: fixed;
}}
.stApp > header {{ background-color: transparent; }}
.block-container {{
    background-color: rgba(14, 17, 23, 0.85); 
    padding-top: 5rem !important; padding-right: 2rem; padding-bottom: 2rem; padding-left: 2rem;
    margin-top: 2rem; border-radius: 15px;
}}
.tarjeta-cliente {{
    background-color: rgba(255, 255, 255, 0.1);
    padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid #444;
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

# ---------------- LÓGICA DE CADUCIDAD ----------------
def limpiar_apartados_vencidos():
    limite_fecha = datetime.now() - timedelta(days=3)
    vencidos = col_apartados.find({"fecha_apartado": {"$lt": limite_fecha}})
    for doc in vencidos:
        campo = doc.get("campo_stock", "stock")
        col_productos.update_one({"_id": doc["producto_id"]}, {"$inc": {campo: 1}})
        col_apartados.delete_one({"_id": doc["_id"]})

limpiar_apartados_vencidos()

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
tipo_busqueda = st.sidebar.selectbox("¿Qué buscas?", ["Bakugans 🔥", "Cartas 🃏", "BakuCores 🛑", "Piezas / Detalles 🛠️"])

if tipo_busqueda == "Bakugans 🔥": sub_filtro = st.sidebar.selectbox("Filtra por Atributo", categorias)
elif tipo_busqueda == "Cartas 🃏": sub_filtro = st.sidebar.selectbox("Filtra por Material", materiales)
elif tipo_busqueda == "BakuCores 🛑": sub_filtro = st.sidebar.selectbox("Filtra por Símbolo", simbolos_core)
else: sub_filtro = "Todos"

es_admin_url = st.query_params.get("jefe") == "1"
vista_admin = "Catálogo" 
admin_autenticado = False

if es_admin_url:
    st.sidebar.markdown("---")
    admin_input = st.sidebar.text_input("🔑 Acceso Admin", type="password")
    if admin_input == st.secrets["ADMIN_PASS"]:
        admin_autenticado = True
        st.sidebar.success("¡Bienvenido, jefe!")
        vista_admin = st.sidebar.radio("Opciones de Administrador", ["Ver Catálogo", "➕ Agregar Producto", "📋 Ver Apartados", "📊 Finanzas y Ventas", "🎨 Personalizar Página"])

st.sidebar.markdown("<div style='height: 400px;'></div>", unsafe_allow_html=True)

# =====================================================================
# ======================== PANTALLA PRINCIPAL =========================
# =====================================================================

if vista_admin == "📊 Finanzas y Ventas":
    st.title("📊 Panel de Analítica Financiera")
    st.markdown("Revisa el rendimiento de tu tienda. KPIs calculados al instante.")
    ventas = list(col_ventas.find({}))
    if not ventas:
        st.info("Aún no tienes ventas registradas para analizar.")
    else:
        hoy = datetime.now()
        def filtrar_por_fecha(dias):
            fecha_limite = hoy - timedelta(days=dias)
            return [v for v in ventas if v["fecha_venta"] >= fecha_limite]
        ventas_hoy = [v for v in ventas if v["fecha_venta"].date() == hoy.date()]
        ventas_semana = filtrar_por_fecha(7)
        ventas_mes = filtrar_por_fecha(30)
        ventas_anio = filtrar_por_fecha(365)
        def calcular_metricas(lista_ventas):
            ingresos = sum(v.get("precio_total", 0) for v in lista_ventas)
            gastos = sum(v.get("gasto_envio", 0) for v in lista_ventas)
            return ingresos, gastos, ingresos - gastos
        tab1, tab2, tab3, tab4 = st.tabs(["Hoy", "Últimos 7 Días", "Últimos 30 Días", "Este Año"])
        datos_tabs = [(tab1, ventas_hoy), (tab2, ventas_semana), (tab3, ventas_mes), (tab4, ventas_anio)]
        for tab, datos_rango in datos_tabs:
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
        nuevo_fondo = st.file_uploader("Fondo de Pantalla HD (Recomendado: Horizontal)", type=["png", "jpg", "jpeg"])
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
    st.title("🛠️ Agregar nuevo producto Multivariante")
    st.markdown("Ahora puedes subir la versión normal y la de detalles en la misma publicación.")
    st.markdown("---")
    tipo_prod = st.radio("Tipo de Producto", ["Bakugan", "Carta", "BakuCore"])
    nombre = st.text_input("Nombre / Descripción principal")
    
    col1, col2, col3 = st.columns(3)
    with col1: atributo_form = st.selectbox("Atributo", categorias[1:], disabled=(tipo_prod != "Bakugan")) 
    with col2: material_form = st.selectbox("Material", materiales[1:], disabled=(tipo_prod != "Carta"))
    with col3: simbolo_form = st.selectbox("Símbolo", simbolos_core[1:], disabled=(tipo_prod != "BakuCore"))
    
    st.markdown("### 🟢 Piezas Normales (Perfectas)")
    c_pn, c_sn = st.columns(2)
    with c_pn: precio = st.number_input("Precio Normal ($)", min_value=0.0, step=10.0)
    with c_sn: stock = st.number_input("Stock Normal", min_value=0, step=1, value=1)
    
    st.markdown("### 🟠 Piezas con Detalles (Desperfectos)")
    con_detalle = st.checkbox("Activar versión con detalles / desperfectos para este producto")
    if con_detalle:
        c_pd, c_sd = st.columns(2)
        with c_pd: precio_detalle = st.number_input("Precio con Detalle ($)", min_value=0.0, step=10.0)
        with c_sd: stock_detalle = st.number_input("Stock con Detalle", min_value=0, step=1, value=1)
        detalle_prod = st.text_input("⚠️ Describe el desperfecto (Ej. Raspón, falta pintura, sin resorte)")
    else:
        precio_detalle, stock_detalle, detalle_prod = 0.0, 0, ""
    
    imagenes_subidas = st.file_uploader("Sube hasta 6 fotos (Frontal, trasera...)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    
    if st.button("Subir Producto al Catálogo"):
        if nombre and imagenes_subidas and (precio > 0 or precio_detalle > 0):
            imagenes_subidas = imagenes_subidas[:6]
            lista_imagenes_b64 = [comprimir_imagen(img) for img in imagenes_subidas]
            
            nuevo_prod = {
                "tipo": tipo_prod, "nombre": nombre, "precio": precio, "stock": stock,
                "precio_detalle": precio_detalle, "stock_detalle": stock_detalle, "detalle": detalle_prod,
                "imagenes_b64": lista_imagenes_b64
            }
            if tipo_prod == "Bakugan": nuevo_prod["atributo"] = atributo_form
            elif tipo_prod == "Carta": nuevo_prod["material"] = material_form
            else: nuevo_prod["simbolo"] = simbolo_form
                
            col_productos.insert_one(nuevo_prod)
            st.success(f"¡{nombre} subido con éxito!")
            st.rerun() 
        else:
            st.error("Falta el nombre, imagen o asignar al menos un precio.")

elif vista_admin == "📋 Ver Apartados":
    st.title("📋 Registro de Clientes y Apartados")
    st.markdown("---")
    todos_los_apartados = list(col_apartados.find({}))
    if not todos_los_apartados:
        st.info("No hay apartados activos en este momento.")
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
            nombres_items = []
            for item in items:
                fecha_str = item["fecha_apartado"].strftime("%d/%m %H:%M")
                precio_item = item.get("precio", 0.0)
                total_cliente += precio_item
                nombres_items.append(item['nombre_producto'])
                st.write(f"- **{item['nombre_producto']}** (${precio_item}) _[Apartado: {fecha_str}]_")
            
            st.markdown(f"**Total piezas a cobrar:** <span style='color:#2ecc71; font-size:1.2em;'>${total_cliente}</span>", unsafe_allow_html=True)
            col_conf, col_canc = st.columns(2)
            with col_conf:
                with st.expander("✅ Confirmar Pago"):
                    cobro_envio = st.number_input("Dinero extra cliente (Envío) $", min_value=0.0, step=10.0, key=f"cobro_{tel}")
                    gastos = st.number_input("Costo de la guía (Paquetería) $", min_value=0.0, step=10.0, key=f"gasto_{tel}")
                    obs = st.text_input("Observaciones", key=f"obs_{tel}")
                    if st.button("Procesar Venta", key=f"btn_venta_{tel}"):
                        col_ventas.insert_one({
                            "cliente": nombre_cliente, "telefono": tel, "productos": nombres_items,
                            "precio_productos": total_cliente, "ingreso_envio": cobro_envio,
                            "precio_total": total_cliente + cobro_envio, "gasto_envio": gastos,
                            "observaciones": obs, "fecha_venta": datetime.now()
                        })
                        for item in items: col_apartados.delete_one({"_id": item["_id"]})
                        st.success("¡Venta registrada!")
                        st.rerun()
            with col_canc:
                with st.expander("🚫 Cancelar Pedido"):
                    if st.button("Confirmar Cancelación", key=f"btn_cancel_{tel}"):
                        for doc in items:
                            campo = doc.get("campo_stock", "stock")
                            col_productos.update_one({"_id": doc["producto_id"]}, {"$inc": {campo: 1}})
                            col_apartados.delete_one({"_id": doc["_id"]})
                        st.success("¡Pedido cancelado y stock devuelto!")
                        st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

else:
    # --- VISTA DEL CATÁLOGO ---
    es_modo_admin_catalogo = admin_autenticado and vista_admin == "Ver Catálogo"
    
    if es_modo_admin_catalogo:
        st.title("🛠️ Administrar Catálogo e Inventario")
        busqueda_texto = st.text_input("🔍 Buscar pieza por nombre...")
    else:
        col_tit, col_busc, col_cart = st.columns([1.5, 2, 1.5])
        with col_tit: st.markdown("### 🔥 Catálogo Libre")
        with col_busc: busqueda_texto = st.text_input("Buscar", placeholder="🔍 ¿Qué estás buscando?", label_visibility="collapsed")
        with col_cart:
            cantidad_carrito = len(st.session_state.carrito)
            total_carrito = sum(item['precio'] for item in st.session_state.carrito)
            with st.popover(f"🛒 Carrito ({cantidad_carrito}) - ${total_carrito}", use_container_width=True):
                if 'wa_link' in st.session_state:
                    st.success("✅ ¡Tus piezas han sido apartadas!")
                    st.markdown(f"[**📲 HAZ CLIC AQUÍ PARA AVISARME POR WHATSAPP**]({st.session_state.wa_link})")
                    if st.button("Cerrar Aviso", use_container_width=True):
                        del st.session_state['wa_link']
                        st.rerun()
                st.markdown("#### Resumen de tu pedido")
                if cantidad_carrito > 0:
                    for i, item in enumerate(st.session_state.carrito):
                        c1, c2 = st.columns([4, 1])
                        c1.markdown(f"<span style='font-size:0.9em;'>{item['nombre']} - **${item['precio']}**</span>", unsafe_allow_html=True)
                        if c2.button("❌", key=f"del_cart_{i}_{item['_id']}"):
                            st.session_state.carrito.pop(i)
                            st.rerun()
                    st.markdown("---")
                    st.markdown(f"**Total a pagar: ${total_carrito}**")
                    nom = st.text_input("Tu Nombre", key="checkout_nom")
                    tel = st.text_input("Tu WhatsApp", key="checkout_tel")
                    
                    if st.button("Confirmar Apartado", use_container_width=True, type="primary"):
                        if nom and tel:
                            for prod_cart in st.session_state.carrito:
                                db_prod = col_productos.find_one({"_id": prod_cart["_id"]})
                                campo_stock = "stock"
                                if prod_cart.get("variante") == "detalle":
                                    campo_stock = "stock_detalle" if "stock_detalle" in db_prod else "stock"
                                    
                                col_apartados.insert_one({
                                    "producto_id": prod_cart["_id"], "nombre_producto": prod_cart["nombre"],
                                    "precio": prod_cart["precio"], "comprador_nombre": nom, "comprador_telefono": tel,
                                    "fecha_apartado": datetime.now(), "campo_stock": campo_stock
                                })
                                col_productos.update_one({"_id": prod_cart["_id"]}, {"$inc": {campo_stock: -1}})
                            texto_wa = f"Hola, acabo de apartar {cantidad_carrito} piezas por un total de ${total_carrito}. Mi nombre es {nom}."
                            st.session_state.wa_link = f"https://wa.me/4462879839?text={texto_wa.replace(' ', '%20')}"
                            st.session_state.carrito = [] 
                            st.rerun()
                        else: st.warning("⚠️ Escribe tu nombre y WhatsApp.")
                else: st.info("Tu carrito está vacío.")

    st.markdown("---")

    # --- LÓGICA DE BÚSQUEDA Y FILTRADO INTELIGENTE MULTIVARIANTE ---
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

    productos_crudos = list(col_productos.find(query_base))
    productos_filtrados = []

    # Filtrar localmente para adaptar a las variables duales (Normal vs Detalle)
    for prod in productos_crudos:
        stock_normal = prod.get('stock', 0)
        stock_detalle = prod.get('stock_detalle', 0)
        texto_detalle = prod.get('detalle', "")
        
        # Corrección mágica para piezas viejas (solo detalle)
        if texto_detalle and 'stock_detalle' not in prod:
            stock_detalle = stock_normal
            stock_normal = 0
            
        if es_modo_admin_catalogo:
            if tipo_busqueda == "Piezas / Detalles 🛠️" and not texto_detalle: continue
            if tipo_busqueda != "Piezas / Detalles 🛠️" and texto_detalle and stock_normal == 0 and stock_detalle > 0: continue
            productos_filtrados.append(prod)
        else:
            if tipo_busqueda == "Piezas / Detalles 🛠️":
                if texto_detalle and stock_detalle > 0: productos_filtrados.append(prod)
            else:
                if stock_normal > 0: productos_filtrados.append(prod)

    if not productos_filtrados:
        st.info("No encontramos ninguna pieza con estos filtros.")
    else:
        cols = st.columns(3)
        for index, prod in enumerate(productos_filtrados):
            with cols[index % 3]:
                st.markdown(f"### {prod['nombre']}")
                
                imagenes_del_producto = prod.get("imagenes_b64", [])
                if not imagenes_del_producto and "imagen_b64" in prod: imagenes_del_producto = [prod["imagen_b64"]]
                
                if imagenes_del_producto:
                    html_galeria = '<div class="galeria-container">'
                    for b64_img in imagenes_del_producto: html_galeria += f'<img src="data:image/jpeg;base64,{b64_img}" class="galeria-img">'
                    html_galeria += '</div>'
                    st.markdown(html_galeria, unsafe_allow_html=True)
                    if len(imagenes_del_producto) > 1: st.markdown("<p style='text-align: center; color: #aaa; font-size: 13px; margin-top: -5px; margin-bottom: 5px;'>👉 Desliza la foto</p>", unsafe_allow_html=True)
                    if st.button("🔍 Ampliar foto", key=f"zoom_{prod['_id']}", use_container_width=True): abrir_zoom(prod['nombre'], imagenes_del_producto)
                
                # VARIABLES LIMPIAS DE STOCK Y PRECIO
                stock_normal = prod.get('stock', 0)
                precio_normal = prod.get('precio', 0.0)
                stock_detalle = prod.get('stock_detalle', 0)
                precio_detalle = prod.get('precio_detalle', 0.0)
                texto_detalle = prod.get('detalle', "")

                # Auto-Migración de lectura
                if texto_detalle and 'stock_detalle' not in prod:
                    stock_detalle = stock_normal
                    precio_detalle = precio_normal
                    stock_normal = 0
                    precio_normal = 0.0
                
                # Renderizar Atributos
                if tipo_busqueda == "Bakugans 🔥": st.write(f"**Atributo:** {prod.get('atributo', 'N/A')}")
                elif tipo_busqueda == "Cartas 🃏": st.write(f"**Material:** {prod.get('material', 'N/A')}")
                elif tipo_busqueda == "BakuCores 🛑": st.write(f"**Símbolo:** {prod.get('simbolo', 'N/A')}")
                
                # VISTA PARA CLIENTES
                if not es_modo_admin_catalogo:
                    en_carrito_normal = sum(1 for item in st.session_state.carrito if item["_id"] == prod["_id"] and item.get("variante") == "normal")
                    en_carrito_detalle = sum(1 for item in st.session_state.carrito if item["_id"] == prod["_id"] and item.get("variante") == "detalle")
                    
                    if stock_normal == 0 and stock_detalle == 0:
                        st.markdown("🚨 **ESTADO:** <span style='color:#e74c3c; font-weight:bold;'>AGOTADO (0)</span>", unsafe_allow_html=True)
                    else:
                        if stock_normal > 0:
                            st.write(f"🟢 **Perfecta:** ${precio_normal} (Disp: {stock_normal})")
                            if (stock_normal - en_carrito_normal) > 0:
                                if st.button(f"🛒 Añadir Normal (${precio_normal})", key=f"add_n_{prod['_id']}", use_container_width=True):
                                    st.session_state.carrito.append({"_id": prod["_id"], "nombre": f"{prod['nombre']}", "precio": precio_normal, "variante": "normal"})
                                    st.rerun()
                            else: st.button("✅ En carrito (Máx)", disabled=True, key=f"max_n_{prod['_id']}", use_container_width=True)
                            
                        if stock_detalle > 0:
                            st.markdown(f"<span style='color:#f39c12; font-size: 0.9em;'>⚠️ **Detalle:** {texto_detalle}</span>", unsafe_allow_html=True)
                            st.write(f"🟠 **C/Detalle:** ${precio_detalle} (Disp: {stock_detalle})")
                            if (stock_detalle - en_carrito_detalle) > 0:
                                if st.button(f"🛒 Añadir c/Detalle (${precio_detalle})", key=f"add_d_{prod['_id']}", use_container_width=True):
                                    st.session_state.carrito.append({"_id": prod["_id"], "nombre": f"{prod['nombre']} (Detalle)", "precio": precio_detalle, "variante": "detalle"})
                                    st.rerun()
                            else: st.button("✅ Detalle en carrito (Máx)", disabled=True, key=f"max_d_{prod['_id']}", use_container_width=True)

                # VISTA PARA ADMINISTRADOR (EDITAR PRECIOS)
                if es_modo_admin_catalogo:
                    st.markdown("---")
                    with st.expander("✏️ Editar Precios y Stock"):
                        np = st.number_input("Precio Normal ($)", value=float(precio_normal), step=10.0, key=f"epn_{prod['_id']}")
                        ns = st.number_input("Stock Normal", value=int(stock_normal), step=1, key=f"esn_{prod['_id']}")
                        ndp = st.number_input("Precio Detalle ($)", value=float(precio_detalle), step=10.0, key=f"epd_{prod['_id']}")
                        nds = st.number_input("Stock Detalle", value=int(stock_detalle), step=1, key=f"esd_{prod['_id']}")
                        ndtxt = st.text_input("Desc. Detalle", value=texto_detalle, key=f"etxt_{prod['_id']}")
                        
                        if st.button("💾 Guardar Cambios", key=f"save_{prod['_id']}", use_container_width=True):
                            col_productos.update_one({"_id": prod["_id"]}, {"$set": {
                                "precio": np, "stock": ns, "precio_detalle": ndp, "stock_detalle": nds, "detalle": ndtxt
                            }})
                            st.success("¡Actualizado!")
                            st.rerun()
                            
                    if st.button("🗑️ Eliminar Producto", key=f"del_{prod['_id']}", use_container_width=True):
                        col_productos.delete_one({"_id": prod["_id"]})
                        st.rerun()