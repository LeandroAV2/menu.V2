// ===== ESTADO =====
let carrito = [];

// ===== INICIALIZAR =====
document.addEventListener('DOMContentLoaded', () => {
  const primeraCat    = Object.keys(MENU_DATA)[0];
  const primeraSubcat = Object.keys(MENU_DATA[primeraCat].subcategorias)[0];
  const primerSubBtn  = document.querySelector(`#sub-${primeraCat} .subcat-btn`);
  if (primerSubBtn) primerSubBtn.classList.add('active');
  renderItems(primeraCat, primeraSubcat);
  if (AUTH_ERROR) abrirModal(AUTH_TAB || 'login');
});

// ===== NAVEGACIÓN =====
function selectCat(catKey, btn) {
  document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.subcat-group').forEach(g => g.classList.remove('open'));
  btn.classList.add('active');
  document.getElementById('sub-' + catKey).classList.add('open');
  const primeraSubcat = Object.keys(MENU_DATA[catKey].subcategorias)[0];
  document.querySelectorAll('.subcat-btn').forEach(b => b.classList.remove('active'));
  const primerBtn = document.querySelector(`#sub-${catKey} .subcat-btn`);
  if (primerBtn) primerBtn.classList.add('active');
  renderItems(catKey, primeraSubcat);
}

function selectSubcat(catKey, subcatKey, btn) {
  document.querySelectorAll('.subcat-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderItems(catKey, subcatKey);
}

function renderItems(catKey, subcatKey) {
  const subcat = MENU_DATA[catKey].subcategorias[subcatKey];
  if (!subcat) return;

  document.getElementById('section-title').textContent = subcat.nombre;
  document.getElementById('section-count').textContent = subcat.items.length + ' platos';

  document.getElementById('items-grid').innerHTML = subcat.items.map(item => `
    <div class="item-card">
      <div class="item-emoji">${item.emoji}</div>
      <div class="item-body">
        <div class="item-name">${item.nombre}</div>
        <div class="item-desc">${item.desc}</div>
        <div class="item-footer">
          <div class="item-precio">$${item.precio.toLocaleString('es-AR')}</div>
          <button class="btn-add" onclick="agregarAlCarrito(${item.id}, '${catKey}', '${subcatKey}')" title="Agregar">+</button>
        </div>
      </div>
    </div>
  `).join('');
}

// ===== CARRITO =====
function agregarAlCarrito(id, catKey, subcatKey) {
  const item = MENU_DATA[catKey].subcategorias[subcatKey].items.find(i => i.id === id);
  if (!item) return;
  const existente = carrito.find(i => i.id === id);
  if (existente) { existente.cantidad++; }
  else { carrito.push({ ...item, cantidad: 1 }); }
  actualizarCarritoUI();
  mostrarToast('✓ ' + item.nombre + ' agregado');
}

function agregarMenuDia(nombre, precio, emoji) {
  const existente = carrito.find(i => i.id === 999);
  if (existente) { existente.cantidad++; }
  else { carrito.push({ id: 999, nombre, precio, emoji, cantidad: 1 }); }
  actualizarCarritoUI();
  mostrarToast('✓ Menú del día agregado');
}

function cambiarCantidad(id, delta) {
  const idx = carrito.findIndex(i => i.id === id);
  if (idx === -1) return;
  carrito[idx].cantidad += delta;
  if (carrito[idx].cantidad <= 0) carrito.splice(idx, 1);
  actualizarCarritoUI();
}

function actualizarCarritoUI() {
  const totalItems = carrito.reduce((s, i) => s + i.cantidad, 0);
  document.getElementById('carrito-badge').textContent = totalItems;
  renderCarrito();
}

function renderCarrito() {
  const container = document.getElementById('carrito-items');
  if (carrito.length === 0) {
    container.innerHTML = `
      <div class="carrito-vacio">
        <div class="vacio-icon">🛒</div>
        <p>Tu carrito está vacío.<br>Agregá algo del menú.</p>
      </div>`;
    document.getElementById('carrito-total').textContent = '$0';
    return;
  }
  container.innerHTML = carrito.map(item => `
    <div class="carrito-item">
      <div class="ci-emoji">${item.emoji}</div>
      <div class="ci-info">
        <div class="ci-name">${item.nombre}</div>
        <div class="ci-precio">$${(item.precio * item.cantidad).toLocaleString('es-AR')}</div>
      </div>
      <div class="ci-controls">
        <button class="btn-qty" onclick="cambiarCantidad(${item.id}, -1)">−</button>
        <span class="ci-qty">${item.cantidad}</span>
        <button class="btn-qty" onclick="cambiarCantidad(${item.id}, 1)">+</button>
      </div>
    </div>
  `).join('');
  const total = carrito.reduce((s, i) => s + i.precio * i.cantidad, 0);
  document.getElementById('carrito-total').textContent = '$' + total.toLocaleString('es-AR');
}

function toggleCarrito() {
  document.getElementById('carrito-panel').classList.toggle('open');
  document.getElementById('carrito-overlay').classList.toggle('open');
}

// ===== CONFIRMAR PEDIDO =====
async function confirmarPedido() {
  if (carrito.length === 0) { mostrarToast('Tu carrito está vacío'); return; }
  if (!USUARIO) {
    toggleCarrito();
    mostrarToast('Iniciá sesión para confirmar tu pedido');
    setTimeout(() => abrirModal('login'), 400);
    return;
  }
  const total = carrito.reduce((s, i) => s + i.precio * i.cantidad, 0);
  const items = carrito.map(i => ({ id: i.id, nombre: i.nombre, cantidad: i.cantidad, precio: i.precio }));
  try {
    const resp = await fetch('/pedido', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items, total })
    });
    const data = await resp.json();
    if (data.ok) {
      const resumen = items.map(i => `${i.cantidad}x ${i.nombre}`).join('\n');
      alert(`✅ ¡Pedido confirmado!\n\n${resumen}\n\nTotal: $${total.toLocaleString('es-AR')}\n\n📲 Tu pedido fue enviado a la cocina.`);
      carrito = [];
      actualizarCarritoUI();
      toggleCarrito();
    } else if (data.error === 'no_auth') {
      toggleCarrito();
      abrirModal('login');
    } else {
      mostrarToast('Error al confirmar. Intentá de nuevo.');
    }
  } catch (e) {
    mostrarToast('Error de conexión. Intentá de nuevo.');
  }
}

// ===== MODAL =====
function abrirModal(tab) {
  document.getElementById('modal-overlay').classList.add('open');
  document.getElementById('modal-auth').classList.add('open');
  switchTab(tab || 'login');
}
function cerrarModal() {
  document.getElementById('modal-overlay').classList.remove('open');
  document.getElementById('modal-auth').classList.remove('open');
}
function switchTab(tab) {
  document.getElementById('tab-login').classList.toggle('active', tab === 'login');
  document.getElementById('tab-registro').classList.toggle('active', tab === 'registro');
  document.getElementById('form-login').style.display    = tab === 'login'    ? 'block' : 'none';
  document.getElementById('form-registro').style.display = tab === 'registro' ? 'block' : 'none';
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') cerrarModal(); });

// ===== TOAST =====
function mostrarToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}
