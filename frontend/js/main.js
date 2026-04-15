// main.js - Unified Vehicle Sales System with M-Pesa Instructions
// Works with both index.html and inventory.html

// API Configuration
const API_BASE_URL = 'http://localhost:5001/api';

// State management
let currentUser = null;
let cart = [];
let currentPurchaseId = null;
let allVehicles = []; 
let currentPage = 1;
window.itemsPerPage = 12; // 2 columns x 6 rows = 12 vehicles

// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', function() {
    console.log("DriveSelect AI Engine Initializing...");
    
    // Load user from localStorage
    const savedUser = localStorage.getItem('currentUser');
    if (savedUser) {
        currentUser = JSON.parse(savedUser);
        updateUIForLoggedInUser();
    }
    
    initializeEventListenators();
    loadCart();
    
    // Determine which page we're on and load appropriate content
    const pathname = window.location.pathname;
    const isInventoryPage = pathname.includes('inventory.html');
    const isSearchPage = pathname.includes('search.html');
    const isAdminPage = pathname.includes('admin-dashboard.html');
    const isCartPage = pathname.includes('cart.html');
    
    if (isInventoryPage) {
        // On inventory page - load all vehicles
        console.log("Inventory page detected - loading all vehicles");
        loadAllVehicles();
    } else if (isSearchPage) {
        // On search page - show empty search state
        showEmptySearchState();
    } else if (isAdminPage) {
        // Admin dashboard specific loads
        if (document.getElementById('adminVehiclesTable')) {
            loadAdminVehicles();
        }
        if (document.getElementById('adminPendingPayments')) {
            loadPendingPayments();
        }
        if (document.getElementById('reportContainer')) {
            initializeReports();
        }
    } else if (isCartPage) {
        // Cart page - display cart
        displayCart();
    } else {
        // Home page - load recommendations or featured vehicles
        loadFeaturedVehicles();
    }
    
    // Load user purchases if on purchase history page
    if (document.getElementById('purchasesContainer') && currentUser) {
        loadUserPurchases();
    }
});

// --- LOAD FUNCTIONS FOR DIFFERENT PAGES ---

async function loadAllVehicles() {
    const container = document.getElementById('recommendationsContainer');
    if (!container) return;
    
    container.innerHTML = '<div class="loading-state"><div class="loading-spinner"></div><p>Loading inventory...</p></div>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/vehicles`);
        if (!response.ok) throw new Error('Failed to load vehicles');
        allVehicles = await response.json();
        renderInventoryPage(1);
    } catch (error) {
        console.error('Error loading vehicles:', error);
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-exclamation-triangle"></i>
                <h3>Unable to Load Inventory</h3>
                <p>Please ensure the server is running on port 5001</p>
            </div>
        `;
        const paginationControls = document.getElementById('paginationControls');
        if (paginationControls) paginationControls.innerHTML = '';
        const pageInfo = document.getElementById('pageInfo');
        if (pageInfo) pageInfo.innerHTML = '';
    }
}

async function loadFeaturedVehicles() {
    const container = document.getElementById('recommendationsContainer');
    if (!container) return;
    
    container.innerHTML = '<div class="loading-state"><div class="loading-spinner"></div><p>Loading featured vehicles...</p></div>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/recommendations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ preferences: {} })
        });
        const data = await response.json();
        allVehicles = (data.recommendations || []).slice(0, 12); // Show first 12 on home page
        renderInventoryPage(1);
    } catch (error) {
        console.error('Error loading featured vehicles:', error);
        container.innerHTML = '<p class="error">Failed to connect to backend server.</p>';
    }
}

function showEmptySearchState() {
    const container = document.getElementById('recommendationsContainer');
    if (!container) return;
    
    container.innerHTML = `
        <div class="empty-search-state" style="text-align: center; padding: 60px 20px; color: #94a3b8; background: #1e293b; border-radius: 16px; border: 1px solid rgba(255,255,255,0.05); grid-column: span 2;">
            <i class="fas fa-search" style="font-size: 4rem; margin-bottom: 20px; opacity: 0.5;"></i>
            <h3 style="font-size: 1.3rem; margin-bottom: 10px; color: white;">No Search Performed Yet</h3>
            <p>Use the search filters above to find vehicles that match your criteria.</p>
            <div style="margin-top: 20px;">
                <span style="display: inline-block; background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.3); padding: 6px 12px; border-radius: 20px; margin: 4px; font-size: 0.8rem;">🔍 Search by make (e.g., Toyota)</span>
                <span style="display: inline-block; background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.3); padding: 6px 12px; border-radius: 20px; margin: 4px; font-size: 0.8rem;">💰 Filter by price range</span>
                <span style="display: inline-block; background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.3); padding: 6px 12px; border-radius: 20px; margin: 4px; font-size: 0.8rem;">📅 Filter by year</span>
                <span style="display: inline-block; background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.3); padding: 6px 12px; border-radius: 20px; margin: 4px; font-size: 0.8rem;">⛽ Filter by fuel type</span>
            </div>
        </div>
    `;
}

// --- VEHICLE DISPLAY & PAGINATION ---

async function handleVehicleSearch(e) {
    if (e) e.preventDefault();
    
    const container = document.getElementById('recommendationsContainer');
    if (!container) return;
    
    container.innerHTML = '<div class="loading-state"><div class="loading-spinner"></div><p>Searching vehicles...</p></div>';
    
    const preferences = {
        price: parseFloat(document.getElementById('maxPrice')?.value) || 0,
        year: parseInt(document.getElementById('year')?.value) || 0,
        mileage: parseInt(document.getElementById('maxMileage')?.value) || 0,
        make: document.getElementById('make')?.value || "",
        model: document.getElementById('model')?.value || "",
        fuel_type: document.getElementById('fuelType')?.value || "",
        transmission: document.getElementById('transmission')?.value || ""
    };
    
    try {
        const response = await fetch(`${API_BASE_URL}/recommendations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: currentUser ? currentUser.id : null,
                preferences: preferences
            })
        });
        
        const data = await response.json();
        allVehicles = data.recommendations || [];
        renderInventoryPage(1);
    } catch (error) {
        console.error('Search error:', error);
        container.innerHTML = '<div class="empty-state"><i class="fas fa-exclamation-triangle"></i><h3>Backend Offline</h3><p>Ensure Flask is running on port 5001.</p></div>';
    }
}

function renderInventoryPage(page) {
    if (!allVehicles || allVehicles.length === 0) {
        const container = document.getElementById('recommendationsContainer');
        if (container) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-car"></i>
                    <h3>No Vehicles Found</h3>
                    <p>No vehicles match your current criteria.</p>
                </div>
            `;
        }
        const paginationControls = document.getElementById('paginationControls');
        if (paginationControls) paginationControls.innerHTML = '';
        const pageInfo = document.getElementById('pageInfo');
        if (pageInfo) pageInfo.innerHTML = '';
        return;
    }

    currentPage = page;
    const start = (currentPage - 1) * window.itemsPerPage;
    const pageVehicles = allVehicles.slice(start, start + window.itemsPerPage);
    
    // Determine which page we're on for different styling
    const isInventoryPage = window.location.pathname.includes('inventory.html');
    
    // Render vehicles
    const container = document.getElementById('recommendationsContainer');
    if (!container) return;
    
    let html = '<div class="vehicle-grid">';
    pageVehicles.forEach(vehicle => {
        const carImage = vehicle.image_url || 'https://images.unsplash.com/photo-1494976388531-d1058494cdd8?w=500';
        const inCart = cart.some(item => item.id === vehicle.id);
        
        // Different card styling for inventory page (horizontal) vs others (vertical)
        if (isInventoryPage) {
            html += `
                <div class="vehicle-card inventory-card" data-vehicle-id="${vehicle.id}">
                    <div class="vehicle-image-container" onclick="viewVehicleDetails(${vehicle.id})">
                        <img src="${carImage}" alt="${vehicle.make} ${vehicle.model}" loading="lazy">
                    </div>
                    <div class="card-meta">
                        <div class="card-header">
                            <h4 onclick="viewVehicleDetails(${vehicle.id})">${vehicle.year} ${vehicle.make} ${vehicle.model}</h4>
                            <p class="price">KSh ${Number(vehicle.price).toLocaleString()}</p>
                        </div>
                        <div class="specs">
                            <span><i class="fas fa-tachometer-alt"></i> ${(vehicle.mileage || 0).toLocaleString()} mi</span>
                            <span><i class="fas fa-gas-pump"></i> ${vehicle.fuel_type || 'N/A'}</span>
                            <span><i class="fas fa-cogs"></i> ${vehicle.transmission || 'N/A'}</span>
                        </div>
                        <div class="description-preview">
                            ${vehicle.description ? vehicle.description.substring(0, 80) + '...' : 'No description available.'}
                        </div>
                        <div class="btn-group">
                            <button class="btn-view" onclick="viewVehicleDetails(${vehicle.id})">
                                <i class="fas fa-info-circle"></i> Details
                            </button>
                            ${currentUser ? 
                                `<button class="btn-cart" onclick="addToCart(${vehicle.id})" ${inCart ? 'disabled' : ''}>
                                    <i class="fas fa-cart-plus"></i> ${inCart ? 'In Cart' : 'Cart'}
                                </button>
                                <button class="btn-cash" onclick="initiatePurchase(${vehicle.id}, 'mpesa')">
                                    <i class="fas fa-mobile-alt"></i> Buy
                                </button>` : 
                                `<button class="btn-view" onclick="window.location.href='login.html'">
                                    <i class="fas fa-lock"></i> Login
                                </button>`
                            }
                        </div>
                    </div>
                </div>
            `;
        } else {
            // Standard vertical card for other pages
            html += `
                <div class="vehicle-card" data-vehicle-id="${vehicle.id}">
                    <div class="vehicle-image-container" onclick="viewVehicleDetails(${vehicle.id})">
                        <img src="${carImage}" alt="${vehicle.make} ${vehicle.model}" loading="lazy">
                        ${vehicle.year ? `<div class="badge">${vehicle.year}</div>` : ''}
                    </div>
                    <div class="card-content">
                        <h3 onclick="viewVehicleDetails(${vehicle.id})">${vehicle.make} ${vehicle.model}</h3>
                        <p class="price">KSh${Number(vehicle.price).toLocaleString()}</p>
                        <p class="specs">
                            ${vehicle.transmission || 'Auto'} | ${vehicle.fuel_type || 'Gas'} | ${vehicle.mileage ? vehicle.mileage.toLocaleString() + ' miles' : '0 miles'}
                        </p>
                        <p class="desc">${vehicle.description ? vehicle.description.substring(0, 60) + '...' : 'No description available.'}</p>
                        <div class="btn-group">
                            <button onclick="viewVehicleDetails(${vehicle.id})" class="btn-view">Details</button>
                            ${currentUser ? 
                                `<button onclick="addToCart(${vehicle.id})" class="btn-cart" ${inCart ? 'disabled' : ''}>${inCart ? 'In Cart' : 'Add to Cart'}</button>
                                 <button onclick="initiatePurchase(${vehicle.id}, 'mpesa')" class="btn-buy">M-Pesa Payment</button>
                                 <button onclick="initiatePurchase(${vehicle.id}, 'manual')" class="btn-cash" style="background:#10b981">Pay Cash</button>` : 
                                '<button onclick="window.location.href=\'login.html\'" class="btn-login-prompt">Login to Buy</button>'
                            }
                        </div>
                    </div>
                </div>
            `;
        }
    });
    html += '</div>';
    container.innerHTML = html;
    
    renderPaginationControls();
}

function renderPaginationControls() {
    const totalPages = Math.ceil(allVehicles.length / window.itemsPerPage);
    
    if (totalPages <= 1) {
        const paginationControls = document.getElementById('paginationControls');
        if (paginationControls) paginationControls.innerHTML = '';
        const pageInfo = document.getElementById('pageInfo');
        if (pageInfo) pageInfo.innerHTML = '';
        return;
    }
    
    // Get or create pagination wrapper
    let paginationWrapper = document.getElementById('paginationControls');
    if (!paginationWrapper) {
        paginationWrapper = document.createElement('div');
        paginationWrapper.id = 'paginationControls';
        paginationWrapper.className = 'pagination-wrapper';
        
        const container = document.getElementById('recommendationsContainer');
        if (container && container.parentNode) {
            container.parentNode.insertBefore(paginationWrapper, container.nextSibling);
        }
    }
    
    // Create page info element if it doesn't exist
    let pageInfoEl = document.getElementById('pageInfo');
    if (!pageInfoEl) {
        pageInfoEl = document.createElement('div');
        pageInfoEl.id = 'pageInfo';
        pageInfoEl.className = 'page-info';
        if (paginationWrapper.parentNode) {
            paginationWrapper.parentNode.insertBefore(pageInfoEl, paginationWrapper.nextSibling);
        }
    }
    
    // Build pagination HTML
    let paginationHtml = `
        <button class="page-btn prev-btn" ${currentPage === 1 ? 'disabled' : ''} onclick="goToPage(${currentPage - 1})">
            <i class="fas fa-chevron-left"></i> Prev
        </button>
        <div class="pagination-numbers">
    `;
    
    const maxVisiblePages = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
    let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);
    
    if (endPage - startPage + 1 < maxVisiblePages) {
        startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }
    
    if (startPage > 1) {
        paginationHtml += `<div class="page-number" onclick="goToPage(1)">1</div>`;
        if (startPage > 2) {
            paginationHtml += `<span class="page-ellipsis">...</span>`;
        }
    }
    
    for (let i = startPage; i <= endPage; i++) {
        paginationHtml += `<div class="page-number ${i === currentPage ? 'active' : ''}" onclick="goToPage(${i})">${i}</div>`;
    }
    
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            paginationHtml += `<span class="page-ellipsis">...</span>`;
        }
        paginationHtml += `<div class="page-number" onclick="goToPage(${totalPages})">${totalPages}</div>`;
    }
    
    paginationHtml += `
        </div>
        <button class="page-btn next-btn" ${currentPage === totalPages ? 'disabled' : ''} onclick="goToPage(${currentPage + 1})">
            Next <i class="fas fa-chevron-right"></i>
        </button>
    `;
    
    paginationWrapper.innerHTML = paginationHtml;
    
    // Update page info
    const start = (currentPage - 1) * window.itemsPerPage + 1;
    const end = Math.min(currentPage * window.itemsPerPage, allVehicles.length);
    pageInfoEl.innerHTML = `Showing ${start} - ${end} of ${allVehicles.length} vehicles`;
}

// Global page navigation function
function goToPage(page) {
    if (page < 1 || page > Math.ceil(allVehicles.length / window.itemsPerPage)) return;
    currentPage = page;
    renderInventoryPage(currentPage);
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function viewVehicleDetails(vehicleId) {
    window.location.href = `vehicle-details.html?id=${vehicleId}`;
}

// --- CART FUNCTIONALITY ---
function loadCart() {
    const savedCart = localStorage.getItem('cart');
    if (savedCart) {
        try {
            cart = JSON.parse(savedCart);
        } catch (e) {
            cart = [];
        }
    }
    updateCartUI();
}

function saveCart() {
    localStorage.setItem('cart', JSON.stringify(cart));
    updateCartUI();
}

async function addToCart(vehicleId) {
    if (!currentUser) {
        alert("Please login to add items to your cart.");
        window.location.href = 'login.html';
        return;
    }
    
    if (cart.some(item => item.id === vehicleId)) {
        alert("This vehicle is already in your cart.");
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/vehicles/${vehicleId}`);
        if (!response.ok) throw new Error('Vehicle not found');
        const vehicle = await response.json();
        
        cart.push(vehicle);
        saveCart();
        alert(`${vehicle.make} ${vehicle.model} added to cart!`);
        
        // Re-render current page to update button states
        renderInventoryPage(currentPage);
    } catch (error) {
        console.error('Error adding to cart:', error);
        alert('Could not add vehicle to cart.');
    }
}

function removeFromCart(vehicleId) {
    cart = cart.filter(item => item.id !== vehicleId);
    saveCart();
    if (typeof displayCart === 'function') displayCart();
}

function updateCartUI() {
    const countEl = document.getElementById('cartCount');
    if (countEl) {
        countEl.innerText = cart.length;
        countEl.style.display = cart.length > 0 ? 'inline-block' : 'none';
    }
    
    const cartTotalEl = document.getElementById('cartTotal');
    if (cartTotalEl) {
        const total = cart.reduce((sum, item) => sum + (item.price || 0), 0);
        cartTotalEl.innerText = `KSh${total.toLocaleString()}`;
    }
}

function displayCart() {
    const container = document.getElementById('cartItems');
    if (!container) return;
    
    if (cart.length === 0) {
        container.innerHTML = '<p class="empty-cart">Your cart is empty.</p>';
        const checkoutBtn = document.getElementById('checkoutBtn');
        if (checkoutBtn) checkoutBtn.style.display = 'none';
        return;
    }
    
    let html = '';
    let total = 0;
    
    cart.forEach(item => {
        total += item.price || 0;
        html += `
            <div class="cart-item" data-id="${item.id}">
                <img src="${item.image_url || 'https://via.placeholder.com/100'}" alt="${item.make} ${item.model}">
                <div class="item-details">
                    <h4>${item.year} ${item.make} ${item.model}</h4>
                    <p>${item.transmission || 'Auto'} | ${item.fuel_type || 'Gas'} | ${item.mileage ? item.mileage.toLocaleString() + ' miles' : ''}</p>
                    <p class="item-price">KSh${Number(item.price).toLocaleString()}</p>
                </div>
                <button onclick="removeFromCart(${item.id})" class="remove-btn">Remove</button>
            </div>
        `;
    });
    
    html += `
        <div class="cart-summary">
            <h3>Total: KSh${total.toLocaleString()}</h3>
            <button onclick="checkout()" class="checkout-btn" id="checkoutBtn">Proceed to Checkout</button>
        </div>
    `;
    
    container.innerHTML = html;
}

async function checkout() {
    if (cart.length === 0) {
        alert("Cart is empty");
        return;
    }
    
    const method = confirm("Pay with M-Pesa? (Cancel for Cash/Manual)") ? 'mpesa' : 'manual';
    initiatePurchase(cart[0].id, method);
}

// --- AUTHENTICATION ---
async function handleLogin(e) {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target).entries());
    
    try {
        const response = await fetch(`${API_BASE_URL}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        if (response.ok) {
            localStorage.setItem('currentUser', JSON.stringify(result.user));
            currentUser = result.user;
            window.location.href = result.user.role === 'admin' ? 'admin-dashboard.html' : 'index.html';
        } else {
            alert('Login failed: ' + (result.error || 'Invalid credentials'));
        }
    } catch (error) {
        alert('Server offline. Ensure Flask is running on port 5001.');
    }
}

async function handleRegistration(e) {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target).entries());
    data.role = 'customer';
    
    try {
        const response = await fetch(`${API_BASE_URL}/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        if (response.ok) {
            alert('Registration successful! Please log in.');
            window.location.href = 'login.html';
        } else {
            alert('Registration failed: ' + result.error);
        }
    } catch (error) {
        alert('Could not connect to server.');
    }
}

function handleLogout() {
    fetch(`${API_BASE_URL}/logout`, { method: 'POST' }).catch(() => {});
    localStorage.removeItem('currentUser');
    localStorage.removeItem('cart');
    cart = [];
    window.location.href = 'index.html';
}

async function handleForgotPassword(e) {
    e.preventDefault();
    const email = document.getElementById('resetEmail').value;
    
    try {
        const response = await fetch(`${API_BASE_URL}/forgot-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        const data = await response.json();
        
        if (response.ok) {
            if (data.debug_token) {
                alert(`Reset token generated (DEBUG): ${data.debug_token}\n\nIn production, this would be emailed to you.`);
            } else {
                alert("Password reset instructions sent to your email!");
            }
        } else {
            alert(data.error || 'Error processing request');
        }
    } catch (err) { 
        alert('Server error. Please try again.');
    }
}

async function handleResetPassword(e) {
    e.preventDefault();
    const token = document.getElementById('resetToken').value;
    const newPassword = document.getElementById('newPassword').value;
    
    try {
        const response = await fetch(`${API_BASE_URL}/reset-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token, password: newPassword })
        });
        const data = await response.json();
        
        if (response.ok) {
            alert("Password reset successful! Please log in.");
            window.location.href = 'login.html';
        } else {
            alert(data.error || 'Error resetting password');
        }
    } catch (err) {
        alert('Server error. Please try again.');
    }
}

// --- M-PESA PAYMENT INSTRUCTIONS ---

async function initiatePurchase(vehicleId, method) {
    if (!currentUser) {
        alert("Please login to make a purchase");
        window.location.href = 'login.html';
        return;
    }
    
    // Get vehicle details
    let vehicle = allVehicles.find(v => v.id === vehicleId);
    if (!vehicle) {
        try {
            const response = await fetch(`${API_BASE_URL}/vehicles/${vehicleId}`);
            vehicle = await response.json();
        } catch (error) {
            alert('Could not load vehicle details');
            return;
        }
    }
    
    const amount = parseFloat(vehicle.price);
    
    if (method === 'mpesa') {
        showMpesaPaymentInstructions(vehicle, amount);
    } else {
        const payload = {
            vehicle_id: vehicleId,
            amount: amount,
            user_id: currentUser.id,
            payment_method: 'manual',
            phone: "CASH_REF"
        };

        try {
            const response = await fetch(`${API_BASE_URL}/create-payment-intent`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (response.ok) {
                alert("Order Reserved! Please visit the showroom to complete your cash payment.");
                window.location.href = 'purchase-confirmation.html';
            } else {
                alert("Transaction Failed: " + (data.error || "Unknown Error"));
            }
        } catch (error) {
            console.error("Connection Error:", error);
            alert("Server connection failed. Is your Flask backend running?");
        }
    }
}

function showMpesaPaymentInstructions(vehicle, amount) {
    let modal = document.getElementById('mpesaInstructionsModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'mpesaInstructionsModal';
        document.body.appendChild(modal);
    }
    
    const transactionRef = `VEH${vehicle.id}${Date.now()}`;
    const paybillNumber = '174379';
    
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h2><i class="fas fa-mobile-alt"></i> M-Pesa Payment Instructions</h2>
                <span class="close-modal" onclick="closeMpesaInstructionsModal()">&times;</span>
            </div>
            <div class="modal-body">
                <div class="payment-details-card">
                    <h3><i class="fas fa-car"></i> ${vehicle.year} ${vehicle.make} ${vehicle.model}</h3>
                    <p class="amount-due">Amount to Pay: <strong>KSh ${Number(amount).toLocaleString()}</strong></p>
                </div>
                
                <div class="payment-steps">
                    <h3><i class="fas fa-list-ol"></i> Follow these steps:</h3>
                    
                    <div class="step">
                        <div class="step-number">1</div>
                        <div class="step-content">Open <strong>M-Pesa</strong> on your phone</div>
                    </div>
                    
                    <div class="step">
                        <div class="step-number">2</div>
                        <div class="step-content">Select <strong>"Lipa Na M-Pesa"</strong> → <strong>"Paybill"</strong></div>
                    </div>
                    
                    <div class="step">
                        <div class="step-number">3</div>
                        <div class="step-content">
                            Enter Business Number: <strong class="highlight">${paybillNumber}</strong>
                            <button class="copy-btn" onclick="copyToClipboard('${paybillNumber}')"><i class="fas fa-copy"></i> Copy</button>
                        </div>
                    </div>
                    
                    <div class="step">
                        <div class="step-number">4</div>
                        <div class="step-content">
                            Enter Account Number: <strong class="highlight">${transactionRef}</strong>
                            <button class="copy-btn" onclick="copyToClipboard('${transactionRef}')"><i class="fas fa-copy"></i> Copy</button>
                        </div>
                    </div>
                    
                    <div class="step">
                        <div class="step-number">5</div>
                        <div class="step-content">Enter Amount: <strong class="highlight">${Number(amount).toLocaleString()}</strong></div>
                    </div>
                    
                    <div class="step">
                        <div class="step-number">6</div>
                        <div class="step-content">Enter your M-Pesa PIN and confirm payment</div>
                    </div>
                </div>
                
                <div class="payment-note">
                    <i class="fas fa-info-circle"></i>
                    <strong>Important:</strong> After payment, your transaction will be verified within 24 hours.
                </div>
                
                <div class="form-group">
                    <label><i class="fas fa-qrcode"></i> M-Pesa Transaction Code (Optional):</label>
                    <input type="text" id="mpesaTransactionCode" placeholder="e.g., QWERTY1234" />
                    <small>Enter your M-Pesa transaction code for faster verification</small>
                </div>
                
                <div class="modal-actions">
                    <button onclick="submitMpesaPaymentConfirmation(${vehicle.id}, ${amount}, '${transactionRef}')" class="btn-primary">
                        <i class="fas fa-check-circle"></i> I Have Made Payment
                    </button>
                    <button onclick="closeMpesaInstructionsModal()" class="btn-secondary">
                        <i class="fas fa-times"></i> Cancel
                    </button>
                </div>
            </div>
        </div>
    `;
    
    addMpesaModalStyles();
    modal.style.display = 'block';
    document.body.style.overflow = 'hidden';
}

async function submitMpesaPaymentConfirmation(vehicleId, amount, transactionRef) {
    const transactionCode = document.getElementById('mpesaTransactionCode')?.value || '';
    
    if (!currentUser) {
        alert('Please login to complete your purchase');
        window.location.href = 'login.html';
        return;
    }
    
    const submitBtn = document.querySelector('#mpesaInstructionsModal .btn-primary');
    const originalText = submitBtn?.innerHTML || '';
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Submitting...';
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/payments/mpesa-manual`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: currentUser.id,
                vehicle_id: vehicleId,
                amount: amount,
                transaction_reference: transactionRef,
                transaction_code: transactionCode,
                payment_method: 'mpesa_manual'
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            alert(`✅ Payment confirmation submitted!\n\nTransaction reference: ${transactionRef}\n\nWe will verify your payment within 24 hours.`);
            closeMpesaInstructionsModal();
            cart = cart.filter(item => item.id !== vehicleId);
            saveCart();
            window.location.href = 'purchase-confirmation.html';
        } else {
            alert('Error: ' + (data.error || 'Could not submit payment confirmation'));
        }
    } catch (error) {
        console.error('Error submitting payment:', error);
        alert('Connection error. Please try again or contact support.');
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }
    }
}

function closeMpesaInstructionsModal() {
    const modal = document.getElementById('mpesaInstructionsModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        const btn = event.target.closest('.copy-btn');
        const originalHTML = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
        setTimeout(() => {
            btn.innerHTML = originalHTML;
        }, 2000);
    }).catch(err => {
        console.error('Could not copy text: ', err);
        alert('Could not copy. Please select and copy manually.');
    });
}

function addMpesaModalStyles() {
    if (document.getElementById('mpesaModalStyles')) return;
    
    const styles = document.createElement('style');
    styles.id = 'mpesaModalStyles';
    styles.textContent = `
        #mpesaInstructionsModal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.85);
            backdrop-filter: blur(5px);
            z-index: 9999;
            overflow-y: auto;
        }
        #mpesaInstructionsModal .modal-content {
            position: relative;
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            margin: 5% auto;
            padding: 0;
            width: 90%;
            max-width: 550px;
            border-radius: 20px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(59, 130, 246, 0.3);
            animation: modalSlideIn 0.3s ease-out;
        }
        @keyframes modalSlideIn {
            from { opacity: 0; transform: translateY(-50px); }
            to { opacity: 1; transform: translateY(0); }
        }
        #mpesaInstructionsModal .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 25px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            background: rgba(59,130,246,0.1);
            border-radius: 20px 20px 0 0;
        }
        #mpesaInstructionsModal .modal-header h2 {
            margin: 0;
            font-size: 1.4rem;
            color: white;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        #mpesaInstructionsModal .modal-header h2 i { color: #3b82f6; }
        #mpesaInstructionsModal .close-modal {
            font-size: 1.8rem;
            cursor: pointer;
            color: #94a3b8;
            transition: color 0.2s;
            line-height: 1;
        }
        #mpesaInstructionsModal .close-modal:hover { color: #ef4444; }
        #mpesaInstructionsModal .modal-body {
            padding: 25px;
            max-height: 70vh;
            overflow-y: auto;
        }
        .payment-details-card {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            border: 1px solid rgba(59,130,246,0.3);
            text-align: center;
        }
        .payment-details-card h3 { margin: 0 0 10px 0; color: #fff; font-size: 1.2rem; }
        .amount-due { font-size: 1rem; margin: 0; }
        .amount-due strong { color: #10b981; font-size: 1.4rem; }
        .payment-steps { margin: 20px 0; }
        .payment-steps h3 { margin-bottom: 15px; color: #3b82f6; font-size: 1.1rem; }
        .step {
            display: flex;
            align-items: center;
            margin-bottom: 12px;
            padding: 10px;
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
            transition: transform 0.2s;
        }
        .step:hover { transform: translateX(5px); background: rgba(255,255,255,0.08); }
        .step-number {
            width: 30px;
            height: 30px;
            background: #3b82f6;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            margin-right: 15px;
            flex-shrink: 0;
        }
        .step-content { flex: 1; font-size: 0.9rem; }
        .highlight {
            background: #f59e0b;
            color: #000;
            padding: 4px 8px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 0.9rem;
            font-weight: bold;
        }
        .copy-btn {
            background: #334155;
            border: none;
            color: white;
            padding: 4px 10px;
            border-radius: 4px;
            cursor: pointer;
            margin-left: 10px;
            font-size: 0.7rem;
        }
        .copy-btn:hover { background: #475569; }
        .payment-note {
            background: rgba(245,158,11,0.1);
            border-left: 3px solid #f59e0b;
            padding: 12px;
            border-radius: 6px;
            margin: 15px 0;
            font-size: 0.85rem;
        }
        .payment-note i { color: #f59e0b; margin-right: 8px; }
        .form-group { margin-top: 20px; }
        .form-group label { display: block; margin-bottom: 8px; font-weight: 500; color: white; }
        .form-group input {
            width: 100%;
            padding: 12px;
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.2);
            background: #0f172a;
            color: white;
            font-size: 0.9rem;
        }
        .form-group input:focus { outline: none; border-color: #3b82f6; }
        .form-group small { display: block; margin-top: 5px; color: #94a3b8; font-size: 0.7rem; }
        .modal-actions { display: flex; gap: 12px; margin-top: 25px; }
        .modal-actions button { flex: 1; padding: 12px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s; font-size: 0.9rem; }
        .btn-primary { background: #10b981; color: white; }
        .btn-primary:hover { background: #059669; transform: translateY(-2px); }
        .btn-secondary { background: #ef4444; color: white; }
        .btn-secondary:hover { background: #dc2626; transform: translateY(-2px); }
        @media (max-width: 640px) {
            #mpesaInstructionsModal .modal-content { width: 95%; margin: 10% auto; }
            #mpesaInstructionsModal .modal-body { padding: 20px; }
            .step { padding: 8px; }
            .step-number { width: 25px; height: 25px; font-size: 0.8rem; }
            .modal-actions { flex-direction: column; }
        }
    `;
    document.head.appendChild(styles);
}

// --- ADMIN ACTIONS ---
async function handleAddVehicle(e) {
    e.preventDefault();
    
    if (!currentUser || currentUser.role !== 'admin') {
        alert("Admin access required!");
        return;
    }

    const formData = new FormData(e.target);
    const vehicleData = {
        user_id: currentUser.id,
        make: formData.get('make'),
        model: formData.get('model'),
        year: parseInt(formData.get('year')),
        price: parseFloat(formData.get('price')),
        image_url: formData.get('image_url'),
        mileage: parseInt(formData.get('mileage')) || 0,
        fuel_type: formData.get('fuel_type'),
        transmission: formData.get('transmission'),
        engine_size: parseFloat(formData.get('engine_size')) || 0.0,
        color: formData.get('color') || '',
        description: formData.get('description') || ''
    };

    try {
        const response = await fetch(`${API_BASE_URL}/admin/add-vehicle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(vehicleData)
        });

        const data = await response.json();
        
        if (response.ok) {
            alert('Vehicle added successfully!');
            e.target.reset();
            loadAdminVehicles();
        } else {
            alert('Failed: ' + data.error);
        }
    } catch (error) {
        console.error('Admin Error:', error);
        alert('Error adding vehicle');
    }
}

async function loadAdminVehicles() {
    const tableBody = document.getElementById('adminVehiclesTable');
    if (!tableBody) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/vehicles`);
        const vehicles = await response.json();
        
        let html = '';
        vehicles.forEach(v => {
            html += `
                <tr>
                    <td>${v.id}</td>
                    <td>${v.year} ${v.make} ${v.model}</td>
                    <td>KSh${Number(v.price).toLocaleString()}</td>
                    <td>${v.status || 'Available'}</td>
                    <td>
                        <button onclick="editVehicle(${v.id})" class="btn-edit">Edit</button>
                        <button onclick="deleteVehicle(${v.id})" class="btn-delete">Delete</button>
                    </td>
                </tr>
            `;
        });
        
        tableBody.innerHTML = html;
    } catch (error) {
        console.error('Error loading vehicles:', error);
        tableBody.innerHTML = '<tr><td colspan="5">Error loading vehicles</td></tr>';
    }
}

async function deleteVehicle(vehicleId) {
    if (!currentUser || currentUser.role !== 'admin') {
        alert("Admin access required!");
        return;
    }
    
    if (!confirm('Are you sure you want to delete this vehicle?')) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/vehicles/${vehicleId}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: currentUser.id })
        });
        
        if (response.ok) {
            alert('Vehicle deleted successfully');
            loadAdminVehicles();
        } else {
            const data = await response.json();
            alert('Error: ' + data.error);
        }
    } catch (error) {
        console.error('Error deleting vehicle:', error);
        alert('Error deleting vehicle');
    }
}

function editVehicle(vehicleId) {
    window.location.href = `edit-vehicle.html?id=${vehicleId}`;
}

// --- PENDING PAYMENTS (Admin) ---
async function loadPendingPayments() {
    const container = document.getElementById('adminPendingPayments');
    if (!container) return;

    if (!currentUser && localStorage.getItem('currentUser')) {
        currentUser = JSON.parse(localStorage.getItem('currentUser'));
    }
    
    if (!currentUser || currentUser.role !== 'admin') {
        container.innerHTML = '<tr><td colspan="5" style="text-align:center; color: #ef4444;">Admin authentication required</td></tr>';
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/admin/pending-payments?user_id=${currentUser.id}`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) throw new Error(`Server responded with ${response.status}`);
        
        const pendingPayments = await response.json();
        
        if (!pendingPayments || pendingPayments.length === 0) {
            container.innerHTML = '<tr><td colspan="5" style="text-align:center;">No pending verifications</td></tr>';
            return;
        }
        
        container.innerHTML = pendingPayments.map(purchase => `
            <tr data-purchase-id="${purchase.id}">
                <td><strong>#${purchase.id}</strong></td>
                <td>${purchase.user || `User #${purchase.user_id}`}</td>
                <td>${purchase.vehicle || `Vehicle #${purchase.vehicle_id}`}</td>
                <td><strong style="color: #10b981;">KSh${Number(purchase.amount).toLocaleString()}</strong></td>
                <td>
                    <button class="btn-verify" onclick="verifyCashPayment(${purchase.id})">
                        <i class="fas fa-check"></i> Verify Payment
                    </button>
                </td>
            </tr>
        `).join('');
        
    } catch (error) {
        console.error('Error loading pending payments:', error);
        container.innerHTML = `<tr><td colspan="5" style="text-align:center;">Error: ${error.message}</td></tr>`;
    }
}

async function verifyCashPayment(purchaseId) {
    if (!currentUser || currentUser.role !== 'admin') {
        showToast("Admin authentication required!", 'error');
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/admin/verify-purchase/${purchaseId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: currentUser.id })
        });

        const result = await response.json();
        if (response.ok) {
            showToast("✅ Payment verified! Vehicle marked as SOLD.", 'success');
            await loadPendingPayments();
            if (typeof loadAdminVehicles === 'function') loadAdminVehicles();
        } else {
            showToast("Verification failed: " + (result.error || "Unknown error"), 'error');
        }
    } catch (error) {
        console.error("Verification failed:", error);
        showToast("Server connection error: " + error.message, 'error');
    }
}

// --- USER PURCHASES ---
async function loadUserPurchases() {
    const container = document.getElementById('purchasesContainer');
    if (!container || !currentUser) return;

    try {
        const response = await fetch(`${API_BASE_URL}/purchases/user/${currentUser.id}`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) throw new Error("Failed to fetch purchases");

        const purchases = await response.json();

        if (purchases.length === 0) {
            container.innerHTML = '<div class="no-orders">No orders found. <a href="inventory.html">Browse Vehicles</a></div>';
            return;
        }

        container.innerHTML = purchases.map(order => `
            <div class="order-card">
                <div class="order-header">
                    <div>
                        <h3>${order.vehicle?.make || 'Vehicle'} ${order.vehicle?.model || ''}</h3>
                        <span class="order-id">Order #${order.id} • ${new Date(order.created_at).toLocaleDateString()}</span>
                    </div>
                    <span class="status-badge ${order.payment_status === 'completed' ? 'status-success' : 'status-pending'}">
                        ${order.payment_status.replace(/_/g, ' ')}
                    </span>
                </div>
                <div class="order-details">
                    <p>Method: ${(order.payment_method || 'cash').toUpperCase()}</p>
                    <p class="order-price">KSh ${Number(order.amount).toLocaleString()}</p>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error("Load Error:", error);
        container.innerHTML = '<p>Unable to load orders. Please try again later.</p>';
    }
}

// --- REPORT GENERATION ---
function initializeReports() {
    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - 30);
    
    const startDateInput = document.getElementById('startDate');
    const endDateInput = document.getElementById('endDate');
    
    if (startDateInput) startDateInput.value = startDate.toISOString().split('T')[0];
    if (endDateInput) endDateInput.value = endDate.toISOString().split('T')[0];
    
    applyReportFilters();
}

function applyReportFilters() {
    const startDate = document.getElementById('startDate')?.value;
    const endDate = document.getElementById('endDate')?.value;
    const reportType = document.getElementById('reportType')?.value;
    
    if (!startDate || !endDate || !reportType) return;
    
    if (reportType === 'sales') {
        loadSalesReport(startDate, endDate);
    } else if (reportType === 'interactions') {
        loadCustomerInteractions(startDate, endDate);
    }
}

async function loadSalesReport(startDate, endDate) {
    try {
        const response = await fetch(`${API_BASE_URL}/admin/purchases?user_id=${currentUser?.id}`);
        const data = await response.json();
        const container = document.getElementById('reportContainer');
        if (container) {
            container.innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;
        }
    } catch (error) {
        console.error('Error loading sales report:', error);
    }
}

async function loadCustomerInteractions(startDate, endDate) {
    console.log('Loading interactions report');
}

// --- UI UTILITIES ---
function initializeEventListenators() {
    const forms = {
        'loginForm': handleLogin,
        'registerForm': handleRegistration,
        'searchForm': handleVehicleSearch,
        'addVehicleForm': handleAddVehicle,
        'forgotPasswordForm': handleForgotPassword,
        'resetPasswordForm': handleResetPassword
    };

    for (const [id, handler] of Object.entries(forms)) {
        const el = document.getElementById(id);
        if (el) el.addEventListener('submit', handler);
    }
    
    document.querySelectorAll('.close-modal, .cancel-btn').forEach(btn => {
        btn.addEventListener('click', closeModal);
    });
}

function updateUIForLoggedInUser() {
    const loginLink = document.getElementById('loginLink');
    const registerLink = document.getElementById('registerLink');
    const userMenu = document.getElementById('userMenu');
    const authLinkContainer = document.getElementById('authLinkContainer');
    const adminNav = document.getElementById('adminNavigation');
    const adminElements = document.querySelectorAll('.admin-only');
    const authContainer = document.getElementById('authContainer');

    if (currentUser) {
        if (loginLink) loginLink.style.display = 'none';
        if (registerLink) registerLink.style.display = 'none';

        if (authContainer) {
            authContainer.innerHTML = `
                <div class="user-menu">
                    <button class="user-dropdown-btn">
                        <i class="fas fa-user-circle"></i> ${currentUser.username}
                    </button>
                    <div class="user-dropdown">
                        <a href="purchase-confirmation.html"><i class="fas fa-shopping-bag"></i> My Orders</a>
                        <a href="#" onclick="handleLogout()"><i class="fas fa-sign-out-alt"></i> Logout</a>
                    </div>
                </div>
            `;
        }

        if (authLinkContainer) {
            authLinkContainer.innerHTML = `
                <a href="#" class="login-btn" onclick="handleLogout()" style="background: #ef4444;">Logout</a>
            `;
        }

        if (userMenu) {
            userMenu.style.display = 'block';
            userMenu.innerHTML = `
                <div class="user-profile-nav">
                    <span>Welcome, <strong>${currentUser.username}</strong> 
                    <small>(${currentUser.role})</small></span>
                    <button onclick="handleLogout()" class="btn-logout">Logout</button>
                </div>
            `;
        }

        if (adminNav && currentUser.role === 'admin') {
            adminNav.style.display = 'block';
        }

        if (currentUser.role === 'admin') {
            adminElements.forEach(el => el.style.display = 'block');
        } else {
            adminElements.forEach(el => el.style.display = 'none');
        }
    } else {
        if (loginLink) loginLink.style.display = 'block';
        if (registerLink) registerLink.style.display = 'block';
        if (userMenu) userMenu.style.display = 'none';
        
        if (authContainer) {
            authContainer.innerHTML = `<a href="login.html" class="login-btn">Login</a>`;
        }
        
        if (authLinkContainer) {
            authLinkContainer.innerHTML = `<a href="login.html" class="login-btn">Login</a>`;
        }
        
        if (adminNav) adminNav.style.display = 'none';
        adminElements.forEach(el => el.style.display = 'none');
    }
}

function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast-notification ${type}`;
    toast.innerHTML = `<i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i> ${message}`;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function closeModal() {
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => {
        modal.style.display = 'none';
    });
    document.body.style.overflow = 'auto';
}

// --- EXPORT FUNCTIONS FOR HTML ACCESS ---
window.handleLogin = handleLogin;
window.handleRegistration = handleRegistration;
window.handleLogout = handleLogout;
window.handleVehicleSearch = handleVehicleSearch;
window.handleAddVehicle = handleAddVehicle;
window.handleForgotPassword = handleForgotPassword;
window.handleResetPassword = handleResetPassword;
window.initiatePurchase = initiatePurchase;
window.viewVehicleDetails = viewVehicleDetails;
window.addToCart = addToCart;
window.removeFromCart = removeFromCart;
window.checkout = checkout;
window.loadAllVehicles = loadAllVehicles;
window.closeModal = closeModal;
window.closeMpesaInstructionsModal = closeMpesaInstructionsModal;
window.deleteVehicle = deleteVehicle;
window.editVehicle = editVehicle;
window.displayCart = displayCart;
window.renderInventoryPage = renderInventoryPage;
window.loadPendingPayments = loadPendingPayments;
window.loadUserPurchases = loadUserPurchases;
window.verifyCashPayment = verifyCashPayment;
window.copyToClipboard = copyToClipboard;
window.submitMpesaPaymentConfirmation = submitMpesaPaymentConfirmation;
window.showMpesaPaymentInstructions = showMpesaPaymentInstructions;
window.goToPage = goToPage;