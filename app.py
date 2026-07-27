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

# ---------------- CARGAR DISEÑO PERSONALIZADO ----------------
config_data = col_config.find_one({"_id": "sitio_prefs"})
fondo_b64 = config_data.get("fondo_b64") if config_data else None
logo_b64 = config_data.get("logo_b64") if config_data else None

if fondo_b64:
    fondo_css = f"""
    <style>
    .stApp {{
        background-image: url("data:image/png;base64,{fondo_b64}");
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
    </style>
    """
    st.markdown(fondo_css, unsafe_allow_html=True)
else:
    fondo_css = """
    <style>
    .tarjeta-cliente {
        background-color: rgba(255, 255, 255, 0.1);
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 10px;
        border: 1px solid #444;
    }
    </style>
    """
    st.markdown(fondo_css, unsafe_allow_html=True)

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
# NUEVO: Símbolos para los BakuCores
simbolos_core = ["Todos", "Fist (Puño) ✊", "Flaming Fist (Puño en llamas) 🔥✊", "Shield (Escudo) 🛡️", "Magic Shield (Escudo mágico) ✨🛡️", "Helix (Hélice) 🧬"]

# =====================================================================
# =========================== MENÚ LATERAL ============================
# =====================================================================

if logo_b64:
    st.sidebar.image(f"data:image/png;base64,{logo_b64}", use_container_width=True)
else:
    st.sidebar.markdown("### 🛒 Mi Tienda (Sube tu logo en Admin)")

st.sidebar.header("Filtros")

# NUEVO: Agregamos BakuCores a la búsqueda principal
tipo_busqueda = st.sidebar.selectbox("¿Qué buscas?", ["Bakugans 🔥", "Cartas 🃏", "BakuCores 🛑"])

if tipo_busqueda == "Bakugans 🔥":
    sub_filtro = st.sidebar.selectbox("Filtra por Atributo", categorias)
elif tipo_busqueda == "Cartas 🃏":
    sub_filtro = st.sidebar.selectbox("Filtra por Material", materiales)
else:
    sub_filtro = st.sidebar.selectbox("Filtra por Símbolo", simbolos_core)

st.sidebar.markdown("---")
admin_input = st.sidebar.text_input("🔑 Acceso Admin", type="password")

vista_admin = "Catálogo" 

if admin_input == st.secrets["ADMIN_PASS"]:
    st.sidebar.success("¡Bienvenido, jefe!")
    vista_admin = st.sidebar.radio("Opciones de Administrador", ["Ver Catálogo", "➕ Agregar Producto", "📋 Ver Apartados", "🎨 Personalizar Página"])
elif admin_input != "":
    st.sidebar.error("Contraseña incorrecta.")

# =====================================================================
# ======================== PANTALLA PRINCIPAL =========================
# =====================================================================

if vista_admin == "🎨 Personalizar Página":
    st.title("🎨 Personaliza el Diseño de tu Tienda")
    st.markdown("Sube las imágenes directo desde tu computadora para cambiar el fondo y el logo de la página. Se guardarán en tu base de datos.")
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
            else:
                st.warning("No subiste ninguna imagen.")

elif vista_admin == "➕ Agregar Producto":
    st.title("🛠️ Agregar nuevo producto al Catálogo")
    st.markdown("---")
    
    # NUEVO: Se agrega la opción BakuCore
    tipo_prod = st.radio("Tipo de Producto", ["Bakugan", "Carta", "BakuCore"])
    nombre = st.text_input("Nombre / Descripción del Producto")
    
    # Ahora usamos 3 columnas para que los filtros se acomoden bien
    col1, col2, col3 = st.columns(3)
    with col1:
        atributo_form = st.selectbox(
            "Atributo (Bakugans)", 
            categorias[1:], 
            disabled=(tipo_prod != "Bakugan") 
        ) 
    with col2:
        material_form = st.selectbox(
            "Material (Cartas)", 
            materiales[1:], 
            disabled=(tipo_prod != "Carta") 
        )
    with col3:
        simbolo_form = st.selectbox(
            "Símbolo (BakuCores)", 
            simbolos_core[1:], 
            disabled=(tipo_prod != "BakuCore") 
        )
    
    precio = st.number_input("Precio ($)", min_value=0.0, step=10.0)
    stock = st.number_input("Cantidad disponible", min_value=1, step=1)
    imagen_subida = st.file_uploader("Sube la foto", type=["png", "jpg", "jpeg"])
    
    if st.button("Subir Producto"):
        if nombre and imagen_subida and precio > 0:
            bytes_data = imagen_subida.getvalue()
            base64_str = base64.b64encode(bytes_data).decode("utf-8")
            
            nuevo_prod = {
                "tipo": tipo_prod,
                "nombre": nombre,
                "precio": precio,
                "stock": stock,
                "imagen_b64": base64_str
            }
            
            # Guardar la característica correcta según el tipo
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
            st.error("Falta el nombre, la imagen o el precio.")

elif vista_admin == "📋 Ver Apartados":
    st.title("📋 Registro de Clientes y Apartados")
    st.markdown("Aquí verás qué piezas tiene apartadas cada persona y cuánto te deben en total.")
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
            
            st.markdown(f'<div class="tarjeta-cliente" style="background-color: rgba(255, 255, 255, 0.1); padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid #444;">', unsafe_allow_html=True)
            st.markdown(f"#### 👤 {nombre_cliente} | 📞 WA: {tel}")
            
            total_cliente = 0
            for item in items:
                fecha_str = item["fecha_apartado"].strftime("%d/%m %H:%M")
                precio_item = item.get("precio", 0.0)
                total_cliente += precio_item
                
                st.write(f"- **{item['nombre_producto']}** (${precio_item}) _[Apartado: {fecha_str}]_")
            
            st.markdown(f"**Total acumulado:** <span style='color:#2ecc71; font-size:1.2em;'>${total_cliente}</span>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

else:
    # --- VISTA DEL CATÁLOGO PÚBLICO ---
    st.title("🔥 Catálogo Libre")
    st.markdown("Selecciona tus piezas. **OJO:** Tienes 3 días para concretar o se pierden los apartados.")
    st.markdown("---")

    # NUEVO: Lógica de búsqueda adaptada para los 3 tipos de productos
    if tipo_busqueda == "Bakugans 🔥":
        query = {"stock": {"$gt": 0}, "$or": [{"tipo": "Bakugan"}, {"tipo": {"$exists": False}}]}
        if sub_filtro != "Todos":
            query["atributo"] = sub_filtro
    elif tipo_busqueda == "Cartas 🃏":
        query = {"stock": {"$gt": 0}, "tipo": "Carta"}
        if sub_filtro != "Todas":
            query["material"] = sub_filtro
    else: # BakuCores
        query = {"stock": {"$gt": 0}, "tipo": "BakuCore"}
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
                if "imagen_b64" in prod:
                    st.image(base64.b64decode(prod["imagen_b64"]), use_container_width=True)
                
                precio_mostrar = prod.get('precio', 0.0)
                
                # Mostrar la característica correcta dependiendo del tipo de producto
                if tipo_busqueda == "Bakugans 🔥":
                    st.write(f"**Atributo:** {prod.get('atributo', 'N/A')}")
                elif tipo_busqueda == "Cartas 🃏":
                    st.write(f"**Material:** {prod.get('material', 'N/A')}")
                else:
                    st.write(f"**Símbolo:** {prod.get('simbolo', 'N/A')}")
                    
                st.write(f"**Disponibles:** {prod['stock']}")
                st.write(f"**Precio:** ${precio_mostrar}")
                
                with st.expander("🛒 Apartar pieza"):
                    if st.session_state.get(f"apartado_{prod['_id']}", False):
                        st.success("✅ ¡Tu apartado está asegurado!")
                        # CAMBIA ESTE NÚMERO POR TU CELULAR
                        link_wa = f"https://wa.me/4462879839?text=Hola,%20acabo%20de%20apartar%20{prod['nombre']}%20por%20${precio_mostrar}"
                        st.markdown(f"[**📲 HAZ CLIC AQUÍ PARA ENVIARME WHATSAPP**]({link_wa})")
                    else:
                        st.write(f"**Total a pagar:** ${precio_mostrar}")
                        st.caption("🚨 *Nota: El costo de envío es aparte.*")
                        
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