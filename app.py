import streamlit as st
import pymongo
import base64
from datetime import datetime, timedelta

# ---------------- CONFIGURACIÓN DE PÁGINA ----------------
st.set_page_config(
    page_title="Bakugan & Cards Market", 
    page_icon="https://cdn-icons-png.flaticon.com/512/785/785116.png", 
    layout="wide"
)

# ---------------- IMAGEN DE FONDO HD Y ESTILOS ----------------
imagen_de_fondo = "https://images.hdqwalls.com/download/bakugan-battle-brawlers-2v-1920x1080.jpg"

fondo_css = f"""
<style>
.stApp {{
    background-image: url("{imagen_de_fondo}");
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
/* Estilo para las tarjetas de clientes en el Admin */
.tarjeta-cliente {{
    background-color: rgba(255, 255, 255, 0.1);
    padding: 15px;
    border-radius: 10px;
    margin-bottom: 10px;
    border: 1px solid #444;
}}
</style>
"""
st.markdown(fondo_css, unsafe_allow_html=True)

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

# ---------------- LÓGICA DE CADUCIDAD (3 DÍAS) ----------------
def limpiar_apartados_vencidos():
    limite_fecha = datetime.now() - timedelta(days=3)
    vencidos = col_apartados.find({"fecha_apartado": {"$lt": limite_fecha}})
    for doc in vencidos:
        col_productos.update_one(
            {"_id": doc["producto_id"]}, 
            {"$inc": {"stock": 1}}
        )
        col_apartados.delete_one({"_id": doc["_id"]})

limpiar_apartados_vencidos()

# =====================================================================
# ======================== INTERFAZ PRINCIPAL =========================
# =====================================================================

st.title("🔥 Catálogo Libre")
st.markdown("Selecciona tus piezas. **OJO:** Tienes 3 días para concretar o se pierden los apartados.")
st.markdown("---")

# Creamos las pestañas principales
tab_bakugan, tab_cartas, tab_admin = st.tabs(["🔥 Bakugans", "🃏 Cartas", "🔒 Panel Admin"])

# ---------------- PESTAÑA: BAKUGANS ----------------
with tab_bakugan:
    categorias_bkg = ["Todos", "Pyrus 🔥", "Aquos 💧", "Ventus 🍃", "Darkus 🌑", "Haos ✨", "Subterra 🪨"]
    filtro_bkg = st.selectbox("Filtra por Atributo", categorias_bkg, key="filtro_bkg")
    
    # Consultamos (si 'tipo' no existe, asumimos que son los Bakugans viejos)
    query_bkg = {"stock": {"$gt": 0}, "$or": [{"tipo": "Bakugan"}, {"tipo": {"$exists": False}}]} 
    if filtro_bkg != "Todos":
        query_bkg["atributo"] = filtro_bkg

    bakugans = list(col_productos.find(query_bkg))

    if not bakugans:
        st.info("No hay Bakugans disponibles con este atributo por el momento.")
    else:
        cols = st.columns(3)
        for index, bkg in enumerate(bakugans):
            col = cols[index % 3] 
            with col:
                st.markdown(f"### {bkg['nombre']}")
                if "imagen_b64" in bkg:
                    st.image(base64.b64decode(bkg["imagen_b64"]), use_container_width=True)
                
                precio_mostrar = bkg.get('precio', 0.0)
                st.write(f"**Atributo:** {bkg.get('atributo', 'N/A')}")
                st.write(f"**Disponibles:** {bkg['stock']}")
                st.write(f"**Precio:** ${precio_mostrar}")
                
                with st.expander("🛒 Apartar pieza"):
                    if st.session_state.get(f"apartado_{bkg['_id']}", False):
                        st.success("✅ ¡Apartado asegurado (3 días)!")
                        link_wa = f"https://wa.me/521234567890?text=Hola,%20acabo%20de%20apartar%20el%20Bakugan%20{bkg['nombre']}%20por%20${precio_mostrar}"
                        st.markdown(f"[**📲 ENVIAR WHATSAPP PARA ENVÍO**]({link_wa})")
                    else:
                        st.caption("🚨 *Nota: Envío aparte.*")
                        nom = st.text_input("Tu Nombre", key=f"n_b_{bkg['_id']}")
                        tel = st.text_input("Tu WhatsApp", key=f"t_b_{bkg['_id']}")
                        
                        if st.button("Confirmar Apartado", key=f"btn_b_{bkg['_id']}"):
                            if nom and tel:
                                col_apartados.insert_one({
                                    "producto_id": bkg["_id"],
                                    "nombre_producto": bkg["nombre"],
                                    "precio": precio_mostrar,
                                    "comprador_nombre": nom,
                                    "comprador_telefono": tel,
                                    "fecha_apartado": datetime.now()
                                })
                                col_productos.update_one({"_id": bkg["_id"]}, {"$inc": {"stock": -1}})
                                st.session_state[f"apartado_{bkg['_id']}"] = True
                                st.rerun() 
                            else:
                                st.warning("Llena los datos.")

# ---------------- PESTAÑA: CARTAS ----------------
with tab_cartas:
    materiales_crt = ["Todas", "Metálica", "Cartón"]
    filtro_crt = st.selectbox("Filtra por Material", materiales_crt, key="filtro_crt")
    
    query_crt = {"stock": {"$gt": 0}, "tipo": "Carta"} 
    if filtro_crt != "Todas":
        query_crt["material"] = filtro_crt

    cartas = list(col_productos.find(query_crt))

    if not cartas:
        st.info("No hay Cartas disponibles con este material por el momento.")
    else:
        cols_c = st.columns(3)
        for index, crt in enumerate(cartas):
            col_c = cols_c[index % 3] 
            with col_c:
                st.markdown(f"### {crt['nombre']}")
                if "imagen_b64" in crt:
                    st.image(base64.b64decode(crt["imagen_b64"]), use_container_width=True)
                
                precio_mostrar_c = crt.get('precio', 0.0)
                st.write(f"**Material:** {crt.get('material', 'N/A')}")
                st.write(f"**Disponibles:** {crt['stock']}")
                st.write(f"**Precio:** ${precio_mostrar_c}")
                
                with st.expander("🛒 Apartar carta"):
                    if st.session_state.get(f"apartado_{crt['_id']}", False):
                        st.success("✅ ¡Apartado asegurado (3 días)!")
                        link_wa_c = f"https://wa.me/521234567890?text=Hola,%20acabo%20de%20apartar%20la%20Carta%20{crt['nombre']}%20por%20${precio_mostrar_c}"
                        st.markdown(f"[**📲 ENVIAR WHATSAPP PARA ENVÍO**]({link_wa_c})")
                    else:
                        st.caption("🚨 *Nota: Envío aparte.*")
                        nom_c = st.text_input("Tu Nombre", key=f"n_c_{crt['_id']}")
                        tel_c = st.text_input("Tu WhatsApp", key=f"t_c_{crt['_id']}")
                        
                        if st.button("Confirmar Apartado", key=f"btn_c_{crt['_id']}"):
                            if nom_c and tel_c:
                                col_apartados.insert_one({
                                    "producto_id": crt["_id"],
                                    "nombre_producto": crt["nombre"],
                                    "precio": precio_mostrar_c,
                                    "comprador_nombre": nom_c,
                                    "comprador_telefono": tel_c,
                                    "fecha_apartado": datetime.now()
                                })
                                col_productos.update_one({"_id": crt["_id"]}, {"$inc": {"stock": -1}})
                                st.session_state[f"apartado_{crt['_id']}"] = True
                                st.rerun() 
                            else:
                                st.warning("Llena los datos.")

# ---------------- PESTAÑA: ADMIN (OCULTA) ----------------
with tab_admin:
    admin_input = st.text_input("🔑 Contraseña de Administrador", type="password", key="admin_pass")
    
    if admin_input == st.secrets["ADMIN_PASS"]:
        st.success("¡Bienvenido, jefe!")
        
        # Sub-pestañas para organizar las tareas del admin
        sub_tab_agregar, sub_tab_clientes = st.tabs(["➕ Agregar al Catálogo", "📋 Ver Clientes y Apartados"])
        
        with sub_tab_agregar:
            with st.form("form_nuevo_producto", clear_on_submit=True):
                tipo_prod = st.radio("¿Qué vas a subir?", ["Bakugan", "Carta"])
                nombre = st.text_input("Nombre / Descripción del Producto")
                
                # Se muestran ambos selectores, pero luego guardamos el que corresponda
                col1, col2 = st.columns(2)
                with col1:
                    atributo = st.selectbox("Atributo (Si es Bakugan)", categorias_bkg[1:]) 
                with col2:
                    material = st.selectbox("Material (Si es Carta)", materiales_crt[1:])
                
                precio = st.number_input("Precio ($)", min_value=0.0, step=10.0)
                stock = st.number_input("Cantidad disponible", min_value=1, step=1)
                imagen_subida = st.file_uploader("Sube la foto", type=["png", "jpg", "jpeg"])
                
                if st.form_submit_button("Subir Producto"):
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
                        # Guardamos el dato específico dependiendo del tipo
                        if tipo_prod == "Bakugan":
                            nuevo_prod["atributo"] = atributo
                        else:
                            nuevo_prod["material"] = material
                            
                        col_productos.insert_one(nuevo_prod)
                        st.success(f"¡{nombre} subido con éxito!")
                        st.rerun() 
                    else:
                        st.error("Falta el nombre, la imagen o el precio.")
                        
        with sub_tab_clientes:
            st.subheader("📦 Tarjetas de Clientes Activos")
            st.write("Aquí verás qué piezas tiene apartadas cada persona.")
            
            todos_los_apartados = list(col_apartados.find({}))
            
            if not todos_los_apartados:
                st.info("No hay apartados activos en este momento.")
            else:
                # Agrupar apartados por teléfono del cliente
                clientes_dict = {}
                for ap in todos_los_apartados:
                    tel = ap.get("comprador_telefono", "Sin número")
                    if tel not in clientes_dict:
                        clientes_dict[tel] = []
                    clientes_dict[tel].append(ap)
                
                # Mostrar una "Tarjeta" por cliente
                for tel, items in clientes_dict.items():
                    nombre_cliente = items[0].get("comprador_nombre", "Desconocido")
                    
                    st.markdown(f'<div class="tarjeta-cliente">', unsafe_allow_html=True)
                    st.markdown(f"#### 👤 {nombre_cliente} | 📞 WA: {tel}")
                    
                    total_cliente = 0
                    for item in items:
                        fecha_str = item["fecha_apartado"].strftime("%d/%m %H:%M")
                        precio_item = item.get("precio", 0.0)
                        total_cliente += precio_item
                        
                        st.write(f"- **{item['nombre_producto']}** (${precio_item}) _[Apartado: {fecha_str}]_")
                    
                    st.markdown(f"**Total acumulado:** <span style='color:#2ecc71; font-size:1.2em;'>${total_cliente}</span>", unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)

    elif admin_input != "":
        st.error("Contraseña incorrecta.")