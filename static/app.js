const CLOTHES = new Set(["XS", "S", "M", "L", "XL", "XXL"]);
const isAdmin = location.pathname.replace(/\/$/, "") === "/admin";

const state = {
  tab: "catalog",
  products: [],
  meta: null,
  category: "Все",
  clothes: new Set(),
  shoes: new Set(),
  sort: "default",
  filtersOpen: false,
  sheet: null,
  sheetSize: "",
  editSizes: new Set(),
};

const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {
  try {
    tg.ready();
    tg.expand();
    tg.setHeaderColor("#000000");
    tg.setBackgroundColor("#000000");
  } catch (_error) {
    /* older Telegram clients */
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function money(value) {
  const currency = (state.meta && state.meta.currency) || "₽";
  return `${new Intl.NumberFormat("ru-RU").format(value)} ${currency}`;
}

function loadFav() {
  try {
    return new Set(JSON.parse(localStorage.getItem("tgshop_fav") || "[]"));
  } catch (_error) {
    return new Set();
  }
}

function saveFav(ids) {
  localStorage.setItem("tgshop_fav", JSON.stringify([...ids]));
}

function loadCart() {
  try {
    const rows = JSON.parse(localStorage.getItem("tgshop_cart") || "[]");
    return Array.isArray(rows) ? rows : [];
  } catch (_error) {
    return [];
  }
}

function saveCart(rows) {
  localStorage.setItem("tgshop_cart", JSON.stringify(rows));
}

function heartSvg(on) {
  const fill = on ? "currentColor" : "none";
  return `<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M12 19s-6.2-3.9-6.2-8A3.4 3.4 0 0 1 12 8.2 3.4 3.4 0 0 1 18.2 11c0 4.1-6.2 8-6.2 8z" fill="${fill}" stroke="currentColor" stroke-width="1.6"/></svg>`;
}

function sliderSvg() {
  return `<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M4 12h10M4 17h6"/></svg>`;
}

function toast(text) {
  const node = el("div", "toast", text);
  document.body.append(node);
  setTimeout(() => node.remove(), 1400);
}

function productById(id) {
  return state.products.find((item) => item.id === id);
}

function matches(product) {
  if (state.category !== "Все" && product.category !== state.category) return false;
  const sizes = new Set(product.sizes || []);
  if (!sizes.size) return true;
  const hasClothes = [...sizes].some((size) => CLOTHES.has(size));
  const hasShoes = [...sizes].some((size) => !CLOTHES.has(size));
  if (state.clothes.size) {
    if (!hasClothes || ![...state.clothes].some((size) => sizes.has(size))) return false;
  }
  if (state.shoes.size) {
    if (!hasShoes || ![...state.shoes].some((size) => sizes.has(size))) return false;
  }
  return true;
}

function sorted(items) {
  const copy = [...items];
  copy.sort((a, b) => {
    if (state.sort === "cheap") return a.price - b.price || a.id - b.id;
    if (state.sort === "expensive") return b.price - a.price || a.id - b.id;
    if (state.sort === "new") return (b.created_at || "").localeCompare(a.created_at || "") || b.id - a.id;
    return a.sort_order - b.sort_order || a.id - b.id;
  });
  return copy;
}

function visibleProducts() {
  return sorted(state.products.filter(matches));
}

function filtersActive() {
  return state.clothes.size > 0 || state.shoes.size > 0 || state.sort !== "default";
}

function photoUrl(product) {
  if (!product.has_photo) return "";
  return `/api/media/${product.id}?v=${encodeURIComponent(product.updated_at || "")}`;
}

function renderCards(container, items, emptyText) {
  container.replaceChildren();
  if (!items.length) {
    container.append(el("p", "empty", emptyText));
    return;
  }
  const fav = loadFav();
  items.forEach((product) => {
    const card = el("article", "card");
    card.setAttribute("role", "button");
    card.tabIndex = 0;
    card.setAttribute("aria-label", product.title);
    const photo = el("div", "card-photo");
    const src = photoUrl(product);
    if (src) {
      const image = document.createElement("img");
      image.alt = "";
      image.src = src;
      photo.append(image);
    } else {
      photo.classList.add("placeholder");
    }
    const heart = el("button", fav.has(product.id) ? "heart on" : "heart");
    heart.type = "button";
    heart.setAttribute("aria-label", "В избранное");
    heart.innerHTML = heartSvg(fav.has(product.id));
    heart.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleFav(product.id);
    });
    photo.append(heart);
    card.append(photo, el("div", "price", product.price_label), el("div", "title", product.title));
    card.addEventListener("click", () => openProduct(product));
    container.append(card);
  });
}

function renderGrid() {
  const items = visibleProducts();
  const text = state.products.length ? "Нет вещей с таким фильтром." : "Пока пусто. Позиции добавляет бот-редактор.";
  renderCards(document.getElementById("grid"), items, text);
}

function renderFav() {
  const view = document.getElementById("view-fav");
  const fav = loadFav();
  const items = state.products.filter((product) => fav.has(product.id));
  view.replaceChildren();
  if (!items.length) {
    view.className = "view";
    const block = el("div", "center-block");
    block.append(el("h1", "", "Пока ничего нет"));
    block.append(el("p", "lead", "Добавляйте товары в избранное, нажимая на сердечко"));
    const button = el("button", "primary", "Перейти в каталог");
    button.type = "button";
    button.addEventListener("click", () => showTab("catalog"));
    block.append(button);
    view.append(block);
    return;
  }
  view.className = "view";
  const grid = el("div", "grid");
  renderCards(grid, items, "");
  view.append(grid);
}

function renderCart() {
  const view = document.getElementById("view-cart");
  const lines = loadCart().map((line) => ({ ...line, product: productById(line.id) })).filter((line) => line.product);
  view.replaceChildren();
  view.className = "view";
  view.append(el("h1", "", "Корзина"));
  view.append(el("p", "lead", (state.meta && state.meta.checkout_hint) || ""));
  if (!lines.length) {
    const block = el("div", "center-block");
    block.append(el("h2", "", "Корзина пуста"));
    block.append(el("p", "lead", "Добавьте вещи из каталога, и здесь появятся выбранные позиции."));
    const button = el("button", "primary", "Перейти в каталог");
    button.type = "button";
    button.addEventListener("click", () => showTab("catalog"));
    block.append(button);
    view.append(block);
  } else {
    const wrap = el("div", "lines");
    let total = 0;
    lines.forEach((line) => {
      total += line.product.price * line.qty;
      const row = el("div", "line");
      const src = photoUrl(line.product);
      if (src) {
        const image = document.createElement("img");
        image.alt = "";
        image.src = src;
        row.append(image);
      } else {
        row.append(el("div", "ph"));
      }
      const info = el("div");
      info.append(el("div", "line-title", line.product.title));
      const meta = [line.product.price_label, line.size || ""].filter(Boolean).join(" · ");
      info.append(el("div", "line-meta", meta));
      const qty = el("div", "qty");
      const minus = el("button", "", "−");
      minus.type = "button";
      minus.addEventListener("click", () => changeQty(line, -1));
      const plus = el("button", "", "+");
      plus.type = "button";
      plus.addEventListener("click", () => changeQty(line, 1));
      qty.append(minus, el("span", "", String(line.qty)), plus);
      row.append(info, qty);
      wrap.append(row);
    });
    view.append(wrap, el("div", "total", `Итого ${money(total)}`));
    if (state.meta && state.meta.order_url) {
      const order = el("button", "primary", "Написать в Telegram");
      order.type = "button";
      order.addEventListener("click", openOrder);
      view.append(order);
    }
  }
  const divider = el("div", "divider");
  const terms = el("button", "linkish", "Условия покупки");
  terms.type = "button";
  terms.addEventListener("click", openTerms);
  view.append(divider, terms);
}

function changeQty(line, delta) {
  const cart = loadCart();
  const found = cart.find((item) => item.id === line.id && item.size === line.size);
  if (!found) return;
  found.qty += delta;
  saveCart(cart.filter((item) => item.qty > 0));
  renderCart();
}

function toggleFav(id) {
  const fav = loadFav();
  if (fav.has(id)) fav.delete(id);
  else fav.add(id);
  saveFav(fav);
  if (state.tab === "catalog") renderGrid();
  if (state.tab === "fav") renderFav();
  if (state.sheet && state.sheet.id === id) openProduct(state.sheet);
}

function addToCart(id, size) {
  const cart = loadCart();
  const found = cart.find((item) => item.id === id && item.size === size);
  if (found) found.qty += 1;
  else cart.push({ id, size, qty: 1 });
  saveCart(cart);
}

function showTab(tab) {
  state.tab = tab;
  state.filtersOpen = false;
  syncFilters();
  document.getElementById("grid").classList.toggle("hidden", tab !== "catalog");
  document.querySelector(".tools").classList.toggle("hidden", tab !== "catalog");
  document.getElementById("view-fav").classList.toggle("hidden", tab !== "fav");
  document.getElementById("view-cart").classList.toggle("hidden", tab !== "cart");
  document.querySelectorAll(".nav button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tab);
  });
  if (tab === "catalog") renderGrid();
  if (tab === "fav") renderFav();
  if (tab === "cart") renderCart();
  window.scrollTo(0, 0);
}

function buildChips() {
  const row = document.getElementById("chips");
  row.replaceChildren();
  const filter = document.createElement("button");
  filter.type = "button";
  filter.className = "pill";
  filter.dataset.filterToggle = "1";
  filter.innerHTML = sliderSvg();
  filter.append(document.createTextNode("Фильтры"));
  row.append(filter);
  const names = ["Все", ...((state.meta && state.meta.categories) || [])];
  names.forEach((name) => {
    const chip = el("button", state.category === name ? "chip on" : "chip", name);
    chip.type = "button";
    chip.dataset.category = name;
    row.append(chip);
  });
  syncFilters();
}

function sizeButtons(values, kind, selected) {
  return values.map((value) => {
    const button = el("button", selected.has(value) ? "size on" : "size", value);
    button.type = "button";
    button.dataset.size = value;
    button.dataset.kind = kind;
    return button;
  });
}

function buildFilters() {
  const panel = document.getElementById("filters");
  panel.replaceChildren();
  const clothesTitle = el("h3", "", "РАЗМЕР ОДЕЖДЫ");
  const clothes = el("div", "sizes");
  clothes.append(...sizeButtons((state.meta && state.meta.clothes_sizes) || [], "clothes", state.clothes));
  const shoesTitle = el("h3", "", "РАЗМЕР ОБУВИ");
  const shoes = el("div", "sizes");
  shoes.append(...sizeButtons((state.meta && state.meta.shoe_sizes) || [], "shoe", state.shoes));
  const sortTitle = el("h3", "", "СОРТИРОВКА");
  const sorts = el("div", "sorts");
  [["default", "По умолчанию"], ["cheap", "Дешевле"], ["expensive", "Дороже"], ["new", "Новые"]].forEach(([id, label]) => {
    const button = el("button", state.sort === id ? "sort on" : "sort", label);
    button.type = "button";
    button.dataset.sort = id;
    sorts.append(button);
  });
  panel.append(clothesTitle, clothes, shoesTitle, shoes, sortTitle, sorts);
}

function syncFilters() {
  const button = document.querySelector("[data-filter-toggle]");
  if (button) button.classList.toggle("on", state.filtersOpen || filtersActive());
  document.getElementById("filters").classList.toggle("hidden", !state.filtersOpen);
}

function openProduct(product) {
  state.sheet = product;
  state.sheetSize = "";
  const overlay = document.getElementById("sheet");
  const sheet = el("div", "sheet");
  const src = photoUrl(product);
  if (src) {
    const image = document.createElement("img");
    image.alt = "";
    image.src = src;
    sheet.append(image);
  }
  sheet.append(el("h2", "", product.title));
  sheet.append(el("div", "price", product.price_label));
  if (product.sizes && product.sizes.length) {
    const sizes = el("div", "sizes");
    product.sizes.forEach((size) => {
      const button = el("button", "size", size);
      button.type = "button";
      button.addEventListener("click", () => {
        state.sheetSize = size;
        sizes.querySelectorAll("button").forEach((node) => node.classList.toggle("on", node === button));
      });
      sizes.append(button);
    });
    sheet.append(sizes);
  }
  const add = el("button", "primary", "В корзину");
  add.type = "button";
  add.addEventListener("click", () => {
    if (product.sizes && product.sizes.length && !state.sheetSize) {
      toast("Выберите размер");
      return;
    }
    addToCart(product.id, state.sheetSize || "");
    closeSheet();
    toast("В корзине");
  });
  sheet.append(add);
  overlay.replaceChildren(sheet);
  overlay.classList.remove("hidden");
}

function closeSheet() {
  state.sheet = null;
  document.getElementById("sheet").classList.add("hidden");
}

function openTerms() {
  const overlay = document.getElementById("terms");
  const sheet = el("div", "sheet");
  sheet.append(el("h2", "", "Условия покупки"));
  const text = el("p", "lead");
  text.style.textAlign = "left";
  text.style.whiteSpace = "pre-wrap";
  text.textContent = (state.meta && state.meta.terms) || "";
  const close = el("button", "primary", "Закрыть");
  close.type = "button";
  close.addEventListener("click", closeTerms);
  sheet.append(text, close);
  overlay.replaceChildren(sheet);
  overlay.classList.remove("hidden");
}

function closeTerms() {
  document.getElementById("terms").classList.add("hidden");
}

function openOrder() {
  const url = state.meta && state.meta.order_url;
  if (!url) return;
  if (tg && tg.openTelegramLink && url.includes("t.me")) tg.openTelegramLink(url);
  else if (tg && tg.openLink) tg.openLink(url);
  else window.open(url, "_blank", "noopener");
}

function bindClient() {
  document.getElementById("chips").addEventListener("click", (event) => {
    if (event.target.closest("[data-filter-toggle]")) {
      event.stopPropagation();
      state.filtersOpen = !state.filtersOpen;
      syncFilters();
      return;
    }
    const chip = event.target.closest("[data-category]");
    if (!chip) return;
    state.category = chip.dataset.category;
    buildChips();
    renderGrid();
  });
  document.getElementById("filters").addEventListener("click", (event) => {
    event.stopPropagation();
    const size = event.target.closest("[data-size]");
    if (size) {
      const set = size.dataset.kind === "shoe" ? state.shoes : state.clothes;
      if (set.has(size.dataset.size)) set.delete(size.dataset.size);
      else set.add(size.dataset.size);
      size.classList.toggle("on");
      syncFilters();
      renderGrid();
      return;
    }
    const sort = event.target.closest("[data-sort]");
    if (!sort) return;
    state.sort = sort.dataset.sort;
    document.querySelectorAll("[data-sort]").forEach((node) => node.classList.toggle("on", node === sort));
    syncFilters();
    renderGrid();
  });
  document.querySelectorAll(".nav button").forEach((button) => {
    button.addEventListener("click", () => showTab(button.dataset.tab));
  });
  document.getElementById("sheet").addEventListener("click", (event) => {
    if (event.target.id === "sheet") closeSheet();
  });
  document.getElementById("terms").addEventListener("click", (event) => {
    if (event.target.id === "terms") closeTerms();
  });
  document.addEventListener("click", () => {
    if (!state.filtersOpen) return;
    state.filtersOpen = false;
    syncFilters();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeSheet();
    closeTerms();
    state.filtersOpen = false;
    syncFilters();
  });
}

function tgHeaders(json) {
  const headers = {};
  if (tg && tg.initData) headers["X-Telegram-Init-Data"] = tg.initData;
  if (json) headers["Content-Type"] = "application/json";
  return headers;
}

function errorText(payload) {
  if (!payload) return "Не получилось сохранить";
  if (typeof payload.detail === "string") return payload.detail;
  return "Проверьте поля";
}

function buildAdminSizes() {
  const box = document.getElementById("f-sizes");
  const values = [
    ...((state.meta && state.meta.clothes_sizes) || []),
    ...((state.meta && state.meta.shoe_sizes) || []),
  ];
  box.replaceChildren();
  values.forEach((value) => {
    const button = el("button", state.editSizes.has(value) ? "size on" : "size", value);
    button.type = "button";
    button.addEventListener("click", () => {
      if (state.editSizes.has(value)) state.editSizes.delete(value);
      else state.editSizes.add(value);
      button.classList.toggle("on");
    });
    box.append(button);
  });
}

function resetEditor() {
  document.getElementById("f-id").value = "";
  document.getElementById("f-title").value = "";
  document.getElementById("f-price").value = "";
  document.getElementById("f-category").value = "";
  document.getElementById("f-photo").value = "";
  document.getElementById("f-active").checked = true;
  document.getElementById("f-save").textContent = "Добавить";
  document.getElementById("f-error").textContent = "";
  state.editSizes = new Set();
  buildAdminSizes();
}

function fillEditor(product) {
  document.getElementById("f-id").value = String(product.id);
  document.getElementById("f-title").value = product.title;
  document.getElementById("f-price").value = String(product.price);
  document.getElementById("f-category").value = product.category;
  document.getElementById("f-active").checked = product.active;
  document.getElementById("f-save").textContent = "Сохранить";
  state.editSizes = new Set(product.sizes || []);
  buildAdminSizes();
  window.scrollTo(0, 0);
}

function renderAdminList() {
  const list = document.getElementById("admin-list");
  list.replaceChildren();
  if (!state.products.length) {
    list.append(el("p", "muted", "Пока нет позиций."));
    return;
  }
  state.products.forEach((product) => {
    const row = el("div", product.active ? "admin-row" : "admin-row off");
    const src = photoUrl(product);
    if (src) {
      const image = document.createElement("img");
      image.alt = "";
      image.src = src;
      row.append(image);
    } else {
      row.append(el("div", "ph"));
    }
    const info = el("div");
    info.append(el("div", "", product.title));
    info.append(el("div", "line-meta", `${product.price_label} · ${product.category}`));
    const actions = el("div", "mini");
    const edit = el("button", "", "Править");
    edit.type = "button";
    edit.addEventListener("click", () => fillEditor(product));
    const hide = el("button", "", product.active ? "Скрыть" : "Показать");
    hide.type = "button";
    hide.addEventListener("click", () => patchProduct(product.id, { active: !product.active }));
    const remove = el("button", "", "Удалить");
    remove.type = "button";
    remove.addEventListener("click", () => removeProduct(product.id));
    actions.append(edit, hide, remove);
    row.append(info, actions);
    list.append(row);
  });
}

async function patchProduct(id, fields) {
  const response = await fetch(`/api/admin/products/${id}`, {
    method: "PATCH",
    headers: tgHeaders(true),
    body: JSON.stringify(fields),
  });
  if (!response.ok) {
    document.getElementById("f-error").textContent = errorText(await response.json().catch(() => null));
    return;
  }
  await loadAdmin();
}

async function removeProduct(id) {
  if (!window.confirm("Удалить позицию?")) return;
  const response = await fetch(`/api/admin/products/${id}`, { method: "DELETE", headers: tgHeaders(false) });
  if (!response.ok) {
    document.getElementById("f-error").textContent = errorText(await response.json().catch(() => null));
    return;
  }
  resetEditor();
  await loadAdmin();
}

async function uploadPhoto(id, file) {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`/api/admin/products/${id}/photo`, {
    method: "POST",
    headers: tgHeaders(false),
    body,
  });
  if (!response.ok) throw new Error(errorText(await response.json().catch(() => null)));
}

async function saveEditor(event) {
  event.preventDefault();
  const error = document.getElementById("f-error");
  error.textContent = "";
  const title = document.getElementById("f-title").value.trim();
  const price = Number(String(document.getElementById("f-price").value).replace(/[^\d]/g, ""));
  const category = document.getElementById("f-category").value.trim();
  if (!title || !category || !Number.isFinite(price)) {
    error.textContent = "Заполните название, цену и категорию";
    return;
  }
  const payload = {
    title,
    price,
    category,
    sizes: [...state.editSizes],
    active: document.getElementById("f-active").checked,
  };
  const existing = document.getElementById("f-id").value;
  const response = await fetch(existing ? `/api/admin/products/${existing}` : "/api/admin/products", {
    method: existing ? "PATCH" : "POST",
    headers: tgHeaders(true),
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    error.textContent = errorText(body);
    return;
  }
  const id = existing || (body && body.id);
  const file = document.getElementById("f-photo").files[0];
  if (file && id) {
    try {
      await uploadPhoto(id, file);
    } catch (uploadError) {
      error.textContent = uploadError.message || "Текст сохранён, фото не загрузилось";
      await loadAdmin();
      return;
    }
  }
  resetEditor();
  await loadAdmin();
  toast("Сохранено");
}

async function loadAdmin() {
  const response = await fetch("/api/admin/products", { headers: tgHeaders(false) });
  if (response.status === 401) {
    document.getElementById("editor").classList.add("hidden");
    document.getElementById("admin-list").textContent = "Откройте эту страницу кнопкой в боте-редакторе.";
    return;
  }
  state.products = await response.json();
  renderAdminList();
}

async function bootAdmin() {
  document.getElementById("client").classList.add("hidden");
  document.getElementById("admin").classList.remove("hidden");
  document.getElementById("more").classList.add("hidden");
  state.meta = await fetch("/api/meta").then((response) => response.json());
  document.getElementById("shop-name").textContent = state.meta.shop_name || "Витрина";
  document.title = state.meta.shop_name || "Витрина";
  buildAdminSizes();
  document.getElementById("editor").addEventListener("submit", saveEditor);
  document.getElementById("f-reset").addEventListener("click", resetEditor);
  await loadAdmin();
}

async function bootClient() {
  bindClient();
  document.getElementById("close").addEventListener("click", () => {
    if (tg && tg.close) tg.close();
  });
  document.getElementById("more").addEventListener("click", openTerms);
  try {
    const [meta, products] = await Promise.all([
      fetch("/api/meta").then((response) => response.json()),
      fetch("/api/products").then((response) => response.json()),
    ]);
    state.meta = meta;
    state.products = products;
  } catch (_error) {
    document.getElementById("grid").append(el("p", "empty", "Не удалось открыть каталог."));
    return;
  }
  document.getElementById("shop-name").textContent = state.meta.shop_name || "Витрина";
  document.title = state.meta.shop_name || "Витрина";
  buildChips();
  buildFilters();
  showTab("catalog");
}

document.getElementById("close").addEventListener("click", () => {
  if (tg && tg.close) tg.close();
});

if (isAdmin) bootAdmin();
else bootClient();
