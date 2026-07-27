import streamlit as st
import pymongo
import base64
from datetime import datetime, timedelta

# ---------------- CONFIGURACIÓN DE PÁGINA ----------------
st.set_page_config(
    page_title="Bakugan Market", 
    page_icon="🔥", 
    layout="wide"
)

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

# ---------------- CARGAR DISEÑO PERSONALIZADO (FONDO Y CSS) ----------------
config_data = col_config.find_one({"_id": "sitio_prefs"})
fondo_b64 = config_data.get("fondo_b64") if config_data else None
logo_b64 = config_data.get("logo_b64") if config_data else None

# CSS Global para el fondo, las tarjetas y las nuevas imágenes responsivas
css_global = f"""
<style>
/* Fondo general */
.stApp {{
    {'background-image: url("data:image/png;base64,' + fondo_b64 + '");' if fondo_b64 else ''}
    background-size: cover;
    background-position: center;
    background-repeat: no-repeat;
    background-attachment: fixed;
}}
.stApp > header {{
    background-color: transparent;
}}
.block-container {{
    background-color: rgba(14, 17, 23, 0.85); 
    padding: 2rem;
    border-radius: 15px;
}}
.tarjeta-cliente {{
    background-color: rgba(255, 255, 255, 0.1);
    padding: 15px;
    border-radius: 10px;
    margin-bottom: 10px;
    border: 1px solid #444;
}}

/* REGLA MAGICA PARA LAS FOTOS DE LOS BAKUGANS EN CELULAR */
.producto-img {{
    width: 100%;
    border-radius: 8px;
    object-fit: contain;
    max-height: 250px; /* Tamaño máximo en PC */
    margin-bottom: 10px;
}}

@media (max-width: 768px) {{
    .producto-img {{
        max-height: 160px; /* Se hacen mucho más chaparritos en celular */
        width: auto;
        max-width: 100%;
        display: block;
        margin-left: auto;
        margin-right: auto;
    }}
}}
</style>
"""
st.markdown(css_global, unsafe_allow_html=True)

# ---------------- LÓGICA DE CADUCIDAD (3 DÍAS) ----------------
def limpiar_apartados_vencidos():
    limite_fecha = datetime.now() - timedelta(days=3)
    vencidos = col_apartados.find({"fecha_apartado": {"$lt": limite_fecha}})
    for doc in vencidos:
        col_productos.update_one({"_id": doc["producto_id"]}, {"$inc": {"stock": 1}})
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
    logo_css = f"""
    <style>
    .logo-celular {{
        width: 100%;
        border-radius: 8px;
        margin-bottom: 10px;
    }}
    @media (max-width: 768px) {{
        .logo-celular {{
            width: 45%; 
            margin-left: auto;
            margin-right: auto;
            display: block;
        }}
    }}
    </style>
    <img src="data:image/png;base64,{logo_b64}" class="logo-celular">
    """
    st.sidebar.markdown(logo_css, unsafe_allow_html=True)
else:
    st.sidebar.markdown("### 🛒 Mi Tienda")

st.sidebar.header("Filtros")

tipo_busqueda = st.sidebar.selectbox("¿Qué buscas?", ["Bakugans 🔥", "Cartas 🃏", "BakuCores 🛑"])

if tipo_busqueda == "Bakugans 🔥":
    sub_filtro = st.sidebar.selectbox("Filtra por Atributo", categorias)
elif tipo_busqueda == "Cartas 🃏":
    sub_filtro = st.sidebar.selectbox("Filtra por Material", materiales)
else:
    sub_filtro = st.sidebar.selectbox("Filtra por Símbolo", simbolos_core)

# 🚨 EL CANDADO INVISIBLE Y AUTENTICACIÓN 🚨
es_admin_url = st.query_params.get("jefe") == "1"
vista_admin = "Catálogo" 
admin_autenticado = False

if es_admin_url:
    st.sidebar.markdown("---")
    admin_input = st.sidebar.text_input("🔑 Acceso Admin", type="password")
    
    if admin_input == st.secrets["ADMIN_PASS"]:
        admin_autenticado = True
        st.sidebar.success("¡Bienvenido, jefe!")
        vista_admin = st.sidebar.radio("Opciones de Administrador", [
            "Ver Catálogo", 
            "➕ Agregar Producto", 
            "📋 Ver Apartados", 
            "📊 Finanzas y Ventas", 
            "🎨 Personalizar Página"
        ])
    elif admin_input != "":
        st.sidebar.error("Contraseña incorrecta.")

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
            ganancia = ingresos - gastos
            return ingresos, gastos, ganancia
            
        tab1, tab2, tab3, tab4 = st.tabs(["Hoy", "Últimos 7 Días", "Últimos 30 Días", "Este Año"])
        
        datos_tabs = [(tab1, ventas_hoy), (tab2, ventas_semana), (tab3, ventas_mes), (tab4, ventas_anio)]
        
        for tab, datos_rango in datos_tabs:
            with tab:
                ing, gas, gan = calcular_metricas(datos_rango)
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("📦 Piezas Vendidas", len(datos_rango))
                col2.metric("💸 Ingresos Brutos", f"${ing:,.2f}")
                col3.metric("📉 Gastos (Guías)", f"${gas:,.2f}")
                col4.metric("💰 Ganancia Neta", f"${gan:,.2f}")
                
        st.markdown("---")
        st.subheader("📝 Historial Detallado de Ventas")
        for v in reversed(ventas):
            neta = v.get('precio_total', 0) - v.get('gasto_envio', 0)
            cobro_envio = v.get('ingreso_envio', 0)
            gasto_envio = v.get('gasto_envio', 0)
            fecha_str = v['fecha_venta'].strftime('%d/%m/%Y')
            obs = v.get('observaciones', 'Ninguna')
            
            tarjeta_venta = f"""
            <div style="background-color: rgba(255, 255, 255, 0.05); padding: 12px; border-radius: 8px; margin-bottom: 10px; border-left: 5px solid #2ecc71; border-top: 1px solid rgba(255,255,255,0.1); border-right: 1px solid rgba(255,255,255,0.1); border-bottom: 1px solid rgba(255,255,255,0.1);">
                <div style="font-size: 14px; margin-bottom: 5px;">
                    <span style="color: #aaa;">📅 {fecha_str}</span> &nbsp;|&nbsp; 👤 <b>{v['cliente']}</b>
                </div>
                <div style="font-size: 15px; margin-bottom: 5px;">
                    💰 <b>Ganancia Neta: <span style="color: #2ecc71;">${neta:,.2f}</span></b> &nbsp;|&nbsp; 
                    📦 Cobro Envío: <span style="color: #f1c40f;">${cobro_envio:,.2f}</span> &nbsp;|&nbsp; 
                    📉 Costo Guía: <span style="color: #e74c3c;">${gasto_envio:,.2f}</span>
                </div>
                <div style="font-size: 13px; color: #ccc;">
                    📝 <i>Obs: {obs}</i>
                </div>
            </div>
            """
            st.markdown(tarjeta_venta, unsafe_allow_html=True)

elif vista_admin == "🎨 Personalizar Página":
    st.title("🎨 Personaliza el Diseño de tu Tienda")
    st.markdown("---")
    with st.form("form_personalizacion"):
        nuevo_fondo = st.file_uploader("Fondo de Pantalla HD (Recomendado: Horizontal)", type=["png", "jpg", "jpeg"])
        nuevo_logo = st.file_uploader("Logo del Menú Lateral", type=["png", "jpg", "jpeg"])
        
        if st.form_submit_button("Guardar Diseño"):
            update_data = {}
            if nuevo_fondo:
                bytes_fondo = nuevo_fondo.getvalue()
                update_data["fondo_b64"] = base64.b64encode(bytes_fondo).decode("utf-8")
            if nuevo_logo:
                bytes_logo = nuevo_logo.getvalue()
                update_data["logo_b64"] = base64.b64encode(bytes_logo).decode("utf-8")
                
            if update_data:
                col_config.update_one({"_id": "sitio_prefs"}, {"$set": update_data}, upsert=True)
                st.success("¡Diseño actualizado! Recarga la página para ver los cambios.")
                st.rerun()

elif vista_admin == "➕ Agregar Producto":
    st.title("🛠️ Agregar nuevo producto al Catálogo")
    st.markdown("---")
    
    tipo_prod = st.radio("Tipo de Producto", ["Bakugan", "Carta", "BakuCore"])
    nombre = st.text_input("Nombre / Descripción del Producto")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        atributo_form = st.selectbox("Atributo (Bakugans)", categorias[1:], disabled=(tipo_prod != "Bakugan")) 
    with col2:
        material_form = st.selectbox("Material (Cartas)", materiales[1:], disabled=(tipo_prod != "Carta"))
    with col3:
        simbolo_form = st.selectbox("Símbolo (BakuCores)", simbolos_core[1:], disabled=(tipo_prod != "BakuCore"))
    
    precio = st.number_input("Precio ($)", min_value=0.0, step=10.0)
    stock = st.number_input("Cantidad disponible", min_value=1, step=1)
    
    # NUEVO: Acepta múltiples imágenes
    imagenes_subidas = st.file_uploader("Sube hasta 5 fotos (Frontal, trasera, detalles...)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    
    if st.button("Subir Producto"):
        if nombre and imagenes_subidas and precio > 0:
            if len(imagenes_subidas) > 5:
                st.warning("Has subido más de 5 fotos. Solo se guardarán las primeras 5 para optimizar tu base de datos.")
                imagenes_subidas = imagenes_subidas[:5]
                
            lista_imagenes_b64 = []
            for img in imagenes_subidas:
                bytes_data = img.getvalue()
                lista_imagenes_b64.append(base64.b64encode(bytes_data).decode("utf-8"))
            
            nuevo_prod = {
                "tipo": tipo_prod,
                "nombre": nombre,
                "precio": precio,
                "stock": stock,
                "imagenes_b64": lista_imagenes_b64 # Guardamos el array de fotos
            }
            
            if tipo_prod == "Bakugan":
                nuevo_prod["atributo"] = atributo_form
            elif tipo_prod == "Carta":
                nuevo_prod["material"] = material_form
            else:
                nuevo_prod["simbolo"] = simbolo_form
                
            col_productos.insert_one(nuevo_prod)
            st.success(f"¡{nombre} subido con éxito!")
            st.rerun() 
        else:
            st.error("Falta el nombre, al menos 1 imagen o el precio.")

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
            if tel not in clientes_dict:
                clientes_dict[tel] = []
            clientes_dict[tel].append(ap)
        
        for tel, items in clientes_dict.items():
            nombre_cliente = items[0].get("comprador_nombre", "Desconocido")
            
            st.markdown(f'<div class="tarjeta-cliente">', unsafe_allow_html=True)
            st.markdown(f"#### 👤 {nombre_cliente} | 📞 WA: {tel}")
            
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
                            "cliente": nombre_cliente,
                            "telefono": tel,
                            "productos": nombres_items,
                            "precio_productos": total_cliente,
                            "ingreso_envio": cobro_envio,
                            "precio_total": total_cliente + cobro_envio,
                            "gasto_envio": gastos,
                            "observaciones": obs,
                            "fecha_venta": datetime.now()
                        })
                        for item in items:
                            col_apartados.delete_one({"_id": item["_id"]})
                        st.success("¡Venta registrada!")
                        st.rerun()

            with col_canc:
                with st.expander("🚫 Cancelar Pedido"):
                    if st.button("Confirmar Cancelación", key=f"btn_cancel_{tel}"):
                        for item in items:
                            col_productos.update_one({"_id": item["producto_id"]}, {"$inc": {"stock": 1}})
                            col_apartados.delete_one({"_id": item["_id"]})
                        st.success("¡Pedido cancelado y stock devuelto!")
                        st.rerun()
                        
            st.markdown("</div>", unsafe_allow_html=True)

else:
    # --- VISTA DEL CATÁLOGO PÚBLICO Y ADMIN ---
    es_modo_admin_catalogo = admin_autenticado and vista_admin == "Ver Catálogo"
    
    if es_modo_admin_catalogo:
        st.title("🛠️ Administrar Catálogo e Inventario")
    else:
        st.title("🔥 Catálogo Libre")
    st.markdown("---")

    query = {}
    if not es_modo_admin_catalogo:
        query["stock"] = {"$gt": 0}

    if tipo_busqueda == "Bakugans 🔥":
        query["$or"] = [{"tipo": "Bakugan"}, {"tipo": {"$exists": False}}]
        if sub_filtro != "Todos":
            query["atributo"] = sub_filtro
    elif tipo_busqueda == "Cartas 🃏":
        query["tipo"] = "Carta"
        if sub_filtro != "Todas":
            query["material"] = sub_filtro
    else: 
        query["tipo"] = "BakuCore"
        if sub_filtro != "Todos":
            query["simbolo"] = sub_filtro

    productos = list(col_productos.find(query))

    if not productos:
        st.info("No hay inventario disponible con estos filtros por el momento.")
    else:
        cols = st.columns(3)
        for index, prod in enumerate(productos):
            col = cols[index % 3] 
            with col:
                st.markdown(f"### {prod['nombre']}")
                
                # --- NUEVA LÓGICA DE GALERÍA DE IMÁGENES ---
                # Recuperamos el arreglo nuevo, o el viejo si es un producto antiguo
                imagenes_del_producto = prod.get("imagenes_b64", [])
                if not imagenes_del_producto and "imagen_b64" in prod:
                    imagenes_del_producto = [prod["imagen_b64"]]
                
                if imagenes_del_producto:
                    if len(imagenes_del_producto) == 1:
                        # Si solo tiene 1 foto, se muestra directa con nuestra clase HTML
                        st.markdown(f'<img src="data:image/png;base64,{imagenes_del_producto[0]}" class="producto-img">', unsafe_allow_html=True)
                    else:
                        # Si tiene varias, creamos un sistema de pestañas (tabs)
                        pestanas = st.tabs([f"📸 {i+1}" for i in range(len(imagenes_del_producto))])
                        for i, pestana in enumerate(pestanas):
                            with pestana:
                                st.markdown(f'<img src="data:image/png;base64,{imagenes_del_producto[i]}" class="producto-img">', unsafe_allow_html=True)
                
                # ---------------------------------------------
                
                precio_mostrar = prod.get('precio', 0.0)
                stock_actual = prod.get('stock', 0)
                
                if tipo_busqueda == "Bakugans 🔥":
                    st.write(f"**Atributo:** {prod.get('atributo', 'N/A')}")
                elif tipo_busqueda == "Cartas 🃏":
                    st.write(f"**Material:** {prod.get('material', 'N/A')}")
                else:
                    st.write(f"**Símbolo:** {prod.get('simbolo', 'N/A')}")
                
                if stock_actual == 0:
                    st.markdown("🚨 **ESTADO:** <span style='color:#e74c3c; font-weight:bold;'>AGOTADO (0)</span>", unsafe_allow_html=True)
                else:
                    st.write(f"**Disponibles:** {stock_actual}")
                    
                st.write(f"**Precio:** ${precio_mostrar}")
                
                if stock_actual > 0 and not es_modo_admin_catalogo:
                    with st.expander("🛒 Apartar pieza"):
                        if st.session_state.get(f"apartado_{prod['_id']}", False):
                            st.success("✅ ¡Tu apartado está asegurado!")
                            link_wa = f"https://wa.me/4462879839?text=Hola,%20acabo%20de%20apartar%20{prod['nombre']}%20por%20${precio_mostrar}"
                            st.markdown(f"[**📲 HAZ CLIC AQUÍ PARA ENVIARME WHATSAPP**]({link_wa})")
                        else:
                            st.write(f"**Total a pagar:** ${precio_mostrar}")
                            
                            nom = st.text_input("Tu Nombre", key=f"n_{prod['_id']}")
                            tel = st.text_input("Tu WhatsApp", key=f"t_{prod['_id']}")
                            
                            if st.button("Confirmar Apartado", key=f"btn_{prod['_id']}"):
                                if nom and tel:
                                    col_apartados.insert_one({
                                        "producto_id": prod["_id"],
                                        "nombre_producto": prod["nombre"],
                                        "precio": precio_mostrar,
                                        "comprador_nombre": nom,
                                        "comprador_telefono": tel,
                                        "fecha_apartado": datetime.now()
                                    })
                                    col_productos.update_one({"_id": prod["_id"]}, {"$inc": {"stock": -1}})
                                    st.session_state[f"apartado_{prod['_id']}"] = True
                                    st.rerun() 
                                else:
                                    st.warning("Escribe tu nombre y teléfono para apartarlo.")

                if es_modo_admin_catalogo:
                    st.markdown("---")
                    c_stock, c_del = st.columns(2)
                    with c_stock:
                        add_stk = st.number_input("Sumar piezas", min_value=1, step=1, key=f"add_{prod['_id']}")
                        if st.button("➕ Stock", key=f"btn_stk_{prod['_id']}", use_container_width=True):
                            col_productos.update_one({"_id": prod["_id"]}, {"$inc": {"stock": add_stk}})
                            st.rerun()
                    with c_del:
                        st.write("") 
                        st.write("")
                        if st.button("🗑️ Eliminar", key=f"del_{prod['_id']}", use_container_width=True):
                            col_productos.delete_one({"_id": prod["_id"]})
                            st.rerun()