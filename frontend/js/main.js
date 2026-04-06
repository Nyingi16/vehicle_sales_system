// main.js - Complete Integrated Version
// Vehicle Sales System with AI Recommendations, Cart, and Dual-Path Payment Processing

// API Configuration
const API_BASE_URL = 'http://127.0.0.1:5001/api'; // Flask backend
const PHP_API_URL = 'http://localhost/vehicle_sales_system/php_api';

// State management
let currentUser = null;
let stripe = null;
let cart = [];
let elements = null;
let cardElement = null;

// Pagination state
let allVehicles = []; 
let currentPage = 1;
window.itemsPerPage = 12; 

// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', function() {
    console.log("DriveSelect AI Engine Initializing...");
    
    if (document.getElementById('paymentModal') || document.querySelector('[data-stripe]')) {
        loadStripe();
    }
    
    const savedUser = localStorage.getItem('currentUser');
    if (savedUser) {
        currentUser = JSON.parse(savedUser);
        updateUIForLoggedInUser();
    }
    
    initializeEventListeners();

    const container = document.getElementById('recommendationsContainer');
    if (container) {
        if (document.getElementById('searchForm')) {
            handleVehicleSearch(new Event('submit'));
        } else {
            loadAvailableStock();
        }
    }
    
    loadCart();
    
    if (document.getElementById('adminVehiclesTable')) {
        loadAdminVehicles();
    }
    
    if (document.getElementById('reportContainer')) {
        initializeReports();
    }
});

// --- STRIPE LOADING ---
function loadStripe() {
    if (window.Stripe) {
        stripe = Stripe('your-publishable-key'); // Replace with your actual pk_test_... key
        return;
    }
    
    const stripeScript = document.createElement('script');
    stripeScript.src = 'https://js.stripe.com/v3/';
    stripeScript.onload = () => {
        stripe = Stripe('your-publishable-key');
    };
    document.head.appendChild(stripeScript);
}

// --- EVENT LISTENER SETUP ---
function initializeEventListeners() {
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
    
    const paymentForm = document.getElementById('paymentForm');
    if (paymentForm) {
        paymentForm.addEventListener('submit', handlePaymentSubmit);
    }
    
    const reportFilterBtn = document.getElementById('applyReportFilters');
    if (reportFilterBtn) reportFilterBtn.addEventListener('click', applyReportFilters);
    
    document.querySelectorAll('.close-modal, .cancel-btn').forEach(btn => {
        btn.addEventListener('click', closeModal);
    });
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
            alert("Password reset instructions sent to your email!");
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
            body: JSON.stringify({ token, new_password: newPassword })
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

// --- VEHICLE DISPLAY & PAGINATION ---

async function handleVehicleSearch(e) {
    if (e) e.preventDefault();
    
    const container = document.getElementById('recommendationsContainer');
    if (!container) return;
    
    container.innerHTML = '<div class="loading-spinner"></div><p class="loading">Loading vehicles...</p>';
    
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
        container.innerHTML = '<p class="error">Backend Offline. Ensure Flask is running on port 5001.</p>';
    }
}

async function loadAvailableStock() {
    const container = document.getElementById('recommendationsContainer');
    if (!container) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/recommendations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ preferences: {} })
        });
        const data = await response.json();
        allVehicles = data.recommendations || [];
        renderInventoryPage(1);
    } catch (error) {
        console.error('Error loading stock:', error);
        container.innerHTML = '<p class="error">Failed to connect to backend server.</p>';
    }
}

function renderInventoryPage(page) {
    currentPage = page;
    const container = document.getElementById('recommendationsContainer');
    if (!container) return;

    if (!allVehicles || allVehicles.length === 0) {
        container.innerHTML = '<p class="no-results">No vehicles found matching your criteria.</p>';
        renderPaginationButtons();
        return;
    }

    const start = (page - 1) * window.itemsPerPage;
    const pagedItems = allVehicles.slice(start, start + window.itemsPerPage);

    let html = '<div class="vehicle-grid">';
    pagedItems.forEach(v => {
        const carImage = v.image_url || 'https://images.unsplash.com/photo-1494976388531-d1058494cdd8?w=500';
        const inCart = cart.some(item => item.id === v.id);
        
        html += `
            <div class="vehicle-card" data-vehicle-id="${v.id}">
                <div class="vehicle-image-container" onclick="viewVehicleDetails(${v.id})">
                    <img src="${carImage}" alt="${v.make} ${v.model}" class="vehicle-img" loading="lazy">
                    ${v.year ? `<div class="badge">${v.year}</div>` : ''}
                </div>
                <div class="card-content">
                    <h3 onclick="viewVehicleDetails(${v.id})">${v.make} ${v.model}</h3>
                    <p class="price">$${Number(v.price).toLocaleString()}</p>
                    <p class="specs">
                        ${v.transmission || 'Auto'} | ${v.fuel_type || 'Gas'} | ${v.mileage ? v.mileage.toLocaleString() + ' miles' : '0 miles'}
                    </p>
                    <p class="desc">${v.description ? v.description.substring(0, 60) + '...' : 'No description available.'}</p>
                    <div class="btn-group">
                        <button onclick="viewVehicleDetails(${v.id})" class="btn-view">Details</button>
                        ${currentUser ? 
                            `<button onclick="addToCart(${v.id})" class="btn-cart" ${inCart ? 'disabled' : ''}>${inCart ? 'In Cart' : 'Add to Cart'}</button>
                             <button onclick="initiatePurchase(${v.id}, 'stripe')" class="btn-buy">Pay Online</button>
                             <button onclick="initiatePurchase(${v.id}, 'manual')" class="btn-cash" style="background:#10b981">Pay Cash</button>` : 
                            '<button onclick="window.location.href=\'login.html\'" class="btn-login-prompt">Login to Buy</button>'
                        }
                    </div>
                </div>
            </div>`;
    });
    html += '</div>';
    container.innerHTML = html;
    renderPaginationButtons();
}

function renderPaginationButtons() {
    let controls = document.getElementById('paginationControls');
    
    if (!controls) {
        controls = document.createElement('div');
        controls.id = 'paginationControls';
        controls.className = 'pagination-wrapper';
        
        const inventorySection = document.querySelector('.inventory-section, .inventory-container, .vehicles-section, main');
        if (inventorySection) {
            inventorySection.appendChild(controls);
        } else {
            const container = document.getElementById('recommendationsContainer');
            if (container && container.parentNode) {
                container.parentNode.insertBefore(controls, container.nextSibling);
            }
        }
    }

    const totalPages = Math.ceil(allVehicles.length / window.itemsPerPage);
    
    if (totalPages <= 1) {
        controls.innerHTML = '';
        return;
    }

    let html = '<div class="pagination-controls">';
    
    html += `<button class="page-btn prev-btn" ${currentPage === 1 ? 'disabled' : ''} onclick="renderInventoryPage(${currentPage - 1})">
        <span>&laquo;</span> Prev
    </button>`;
    
    const maxVisiblePages = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
    let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);
    
    if (endPage - startPage + 1 < maxVisiblePages) {
        startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }
    
    if (startPage > 1) {
        html += `<button class="page-btn" onclick="renderInventoryPage(1)">1</button>`;
        if (startPage > 2) {
            html += `<span class="page-ellipsis">...</span>`;
        }
    }
    
    for (let i = startPage; i <= endPage; i++) {
        html += `<button class="page-btn ${i === currentPage ? 'active' : ''}" onclick="renderInventoryPage(${i})">${i}</button>`;
    }
    
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            html += `<span class="page-ellipsis">...</span>`;
        }
        html += `<button class="page-btn" onclick="renderInventoryPage(${totalPages})">${totalPages}</button>`;
    }
    
    html += `<button class="page-btn next-btn" ${currentPage === totalPages ? 'disabled' : ''} onclick="renderInventoryPage(${currentPage + 1})">
        Next <span>&raquo;</span>
    </button>`;
    
    html += '</div>';
    html += `<div class="page-info">
        Showing ${((currentPage - 1) * window.itemsPerPage) + 1} - ${Math.min(currentPage * window.itemsPerPage, allVehicles.length)} of ${allVehicles.length} vehicles
    </div>`;
    
    controls.innerHTML = html;
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
        
        const buttons = document.querySelectorAll(`.vehicle-card[data-vehicle-id="${vehicleId}"] .btn-cart`);
        buttons.forEach(btn => {
            btn.textContent = 'In Cart';
            btn.disabled = true;
        });
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
        cartTotalEl.innerText = `$${total.toLocaleString()}`;
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
                    <p class="item-price">$${Number(item.price).toLocaleString()}</p>
                </div>
                <button onclick="removeFromCart(${item.id})" class="remove-btn">Remove</button>
            </div>
        `;
    });
    
    html += `
        <div class="cart-summary">
            <h3>Total: $${total.toLocaleString()}</h3>
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
    
    const method = confirm("Pay Online with Card? (Cancel for Cash/Manual)") ? 'stripe' : 'manual';
    initiatePurchase(cart[0].id, method);
}

// --- DUAL-PATH PAYMENT PROCESSING ---

/**
 * Initiates purchase flow. 
 * @param {number} vehicleId 
 * @param {string} method - 'stripe' or 'manual'
 */
async function initiatePurchase(vehicleId, method = 'stripe') {
    if (!currentUser) {
        alert('Please log in to make a purchase');
        window.location.href = 'login.html';
        return;
    }

    // Show loading state
    const buyBtn = document.querySelector(`[onclick*="initiatePurchase(${vehicleId}"]`);
    if (buyBtn) {
        buyBtn.textContent = 'Processing...';
        buyBtn.disabled = true;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/create-payment-intent`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                vehicle_id: vehicleId,
                user_id: currentUser.id,
                payment_method: method
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            if (method === 'stripe') {
                // Make sure we have clientSecret
                if (data.clientSecret) {
                    showPaymentModal(data.clientSecret, data.purchase_id);
                } else {
                    alert('Payment system error. Please try again.');
                    if (buyBtn) {
                        buyBtn.textContent = 'Pay Online';
                        buyBtn.disabled = false;
                    }
                }
            } else {
                // Cash payment successful
                alert('Purchase request submitted! Please visit our showroom to complete cash payment.\n\n' +
                      'Our staff will contact you within 24 hours to schedule your visit.');
                
                // Remove from cart if purchased
                cart = cart.filter(item => item.id !== vehicleId);
                saveCart();
                
                // Redirect to confirmation page with purchase ID
                window.location.href = `purchase-confirmation.html?id=${data.purchase_id}&method=cash`;
            }
        } else {
            alert('Error: ' + (data.error || 'Payment processing failed'));
            if (buyBtn) {
                buyBtn.textContent = method === 'stripe' ? 'Pay Online' : 'Pay Cash';
                buyBtn.disabled = false;
            }
        }
    } catch (error) {
        console.error('Payment error:', error);
        alert('Could not connect to payment server. Please try again later.');
        if (buyBtn) {
            buyBtn.textContent = method === 'stripe' ? 'Pay Online' : 'Pay Cash';
            buyBtn.disabled = false;
        }
    }
}
function showPaymentModal(clientSecret, purchaseId) {
    const modal = document.getElementById('paymentModal');
    if (!modal) return;
    
    modal.style.display = 'block';
    document.body.style.overflow = 'hidden';
    modal.dataset.purchaseId = purchaseId;
    modal.dataset.clientSecret = clientSecret;
    
    if (!stripe) { 
        alert('Stripe not loaded. Please refresh the page.');
        return; 
    }
    
    elements = stripe.elements();
    cardElement = elements.create('card', {
        style: {
            base: {
                fontSize: '16px',
                color: '#32325d',
                '::placeholder': {
                    color: '#aab7c4'
                }
            }
        }
    });
    cardElement.mount('#card-element');
}

async function handlePaymentSubmit(e) {
    e.preventDefault();
    const modal = document.getElementById('paymentModal');
    const clientSecret = modal.dataset.clientSecret;
    const purchaseId = modal.dataset.purchaseId;
    const submitBtn = e.target.querySelector('button');
    const errorEl = document.getElementById('paymentError');
    
    if (!stripe || !cardElement) {
        if (errorEl) errorEl.textContent = 'Payment system not initialized';
        return;
    }
    
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Verifying...';
    }

    const {error, paymentIntent} = await stripe.confirmCardPayment(clientSecret, {
        payment_method: { card: cardElement }
    });
    
    if (error) {
        if (errorEl) errorEl.textContent = error.message;
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Pay Now';
        }
    } else if (paymentIntent.status === 'succeeded') {
        await fetch(`${API_BASE_URL}/payment-confirmation`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                payment_intent_id: paymentIntent.id,
                purchase_id: purchaseId
            })
        });
        
        // Remove from cart if purchased
        cart = cart.filter(item => item.id !== purchaseId);
        saveCart();
        
        alert('Payment Successful!');
        closeModal();
        window.location.href = 'purchase-confirmation.html';
    }
}

function closeModal() {
    const modal = document.getElementById('paymentModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
        if (cardElement) {
            cardElement.unmount();
            cardElement = null;
        }
    }
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
                    <td>$${Number(v.price).toLocaleString()}</td>
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
        const response = await fetch(`${API_BASE_URL}/admin/vehicles/${vehicleId}`, {
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
        const response = await fetch(
            `${PHP_API_URL}/reports.php?type=sales&start_date=${startDate}&end_date=${endDate}`
        );
        const data = await response.json();
        displaySalesReport(data);
    } catch (error) {
        console.error('Error loading sales report:', error);
        const container = document.getElementById('reportContainer');
        if (container) container.innerHTML = '<p class="error">Error loading report</p>';
    }
}

async function loadCustomerInteractions(startDate, endDate) {
    try {
        const response = await fetch(
            `${PHP_API_URL}/reports.php?type=interactions&start_date=${startDate}&end_date=${endDate}`
        );
        const data = await response.json();
        displayCustomerInteractions(data);
    } catch (error) {
        console.error('Error loading interactions report:', error);
        const container = document.getElementById('interactionsContainer');
        if (container) container.innerHTML = '<p class="error">Error loading report</p>';
    }
}

function displaySalesReport(data) {
    const container = document.getElementById('reportContainer');
    if (!container) return;
    
    let html = `
        <div class="report-summary">
            <h3>Sales Summary</h3>
            <p>Total Revenue: $${data.summary?.total_revenue?.toLocaleString() || 0}</p>
            <p>Total Transactions: ${data.summary?.total_transactions || 0}</p>
            <p>Unique Customers: ${data.summary?.unique_customers || 0}</p>
            <p>Average Sale: $${data.summary?.average_sale_value?.toLocaleString() || 0}</p>
        </div>
        <div class="report-details">
            <h3>Sales Details</h3>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Vehicle</th>
                        <th>Buyer</th>
                        <th>Amount</th>
                    </tr>
                </thead>
                <tbody>
    `;
    
    if (data.sales_data && data.sales_data.length > 0) {
        data.sales_data.forEach(sale => {
            html += `
                <tr>
                    <td>${sale.sale_date || 'N/A'}</td>
                    <td>${sale.make || ''} ${sale.model || ''}</td>
                    <td>${sale.buyer || 'N/A'}</td>
                    <td>$${sale.revenue?.toLocaleString() || 0}</td>
                </tr>
            `;
        });
    } else {
        html += '<tr><td colspan="4">No sales data available</td></tr>';
    }
    
    html += `
                </tbody>
            </table>
        </div>
    `;
    
    container.innerHTML = html;
}

function displayCustomerInteractions(data) {
    const container = document.getElementById('interactionsContainer');
    if (!container) return;
    container.innerHTML = '<p>Customer interactions report loading...</p>';
}

// --- CRM INSIGHTS ---

async function loadUserInsights(userId) {
    if (!currentUser || currentUser.role !== 'admin') {
        console.log('Admin access required for CRM insights');
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/crm/user-insights/${userId}`, {
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        displayUserInsights(data);
    } catch (error) {
        console.error('Error loading user insights:', error);
    }
}

function displayUserInsights(insights) {
    const container = document.getElementById('insightsContainer');
    if (!container) return;
    
    let html = `
        <div class="insights-card">
            <h3>User Preferences</h3>
            <p><strong>Most Viewed Make:</strong> ${insights.preferences?.most_viewed_make || 'N/A'}</p>
            <p><strong>Price Range:</strong> $${insights.preferences?.price_range?.min || 0} - $${insights.preferences?.price_range?.max || 0}</p>
            <p><strong>Preferred Fuel Types:</strong> ${insights.preferences?.preferred_fuel_types?.join(', ') || 'N/A'}</p>
            <p><strong>Engagement Score:</strong> ${insights.preferences?.engagement_score || 0}</p>
            <p><strong>Purchase Readiness:</strong> ${insights.preferences?.purchase_readiness || 0}%</p>
        </div>
        <div class="insights-card">
            <h3>Interaction Summary</h3>
            <p><strong>Total Interactions:</strong> ${insights.interaction_summary?.total_interactions || 0}</p>
            <p><strong>Views:</strong> ${insights.interaction_summary?.views || 0}</p>
            <p><strong>Favorites:</strong> ${insights.interaction_summary?.favorites || 0}</p>
            <p><strong>Recommendations:</strong> ${insights.interaction_summary?.recommendations || 0}</p>
            <p><strong>Purchases:</strong> ${insights.interaction_summary?.purchases || 0}</p>
        </div>
        <div class="insights-card">
            <h3>Recommended Vehicles</h3>
    `;
    
    if (insights.recommended_vehicles && insights.recommended_vehicles.length > 0) {
        insights.recommended_vehicles.forEach(vehicle => {
            html += `<p>${vehicle.make} ${vehicle.model} (${vehicle.year}) - $${vehicle.price?.toLocaleString()}</p>`;
        });
    } else {
        html += '<p>No recommendations available</p>';
    }
    
    html += '</div>';
    container.innerHTML = html;
}

// --- UI UTILITIES ---

function updateUIForLoggedInUser() {
    const loginLink = document.getElementById('loginLink');
    const registerLink = document.getElementById('registerLink');
    const userMenu = document.getElementById('userMenu');
    const authLinkContainer = document.getElementById('authLinkContainer');
    const adminNav = document.getElementById('adminNavigation');
    const adminElements = document.querySelectorAll('.admin-only');

    if (currentUser) {
        if (loginLink) loginLink.style.display = 'none';
        if (registerLink) registerLink.style.display = 'none';

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
        if (authLinkContainer) {
            authLinkContainer.innerHTML = `<a href="login.html" class="login-btn">Login</a>`;
        }
        if (adminNav) adminNav.style.display = 'none';
        adminElements.forEach(el => el.style.display = 'none');
    }
}
/**
 * Admin: Load purchases specifically waiting for cash verification
 *//**
 * Admin: Fetch and display purchases awaiting cash verification
 */
async function loadPendingPayments() {
    const container = document.getElementById('adminPendingPayments');
    if (!container) return;

    try {
        const response = await fetch(`${API_BASE_URL}/admin/purchases`);
        const purchases = await response.json();
        
        // Only show manual payments that aren't completed yet
        const pending = purchases.filter(p => p.payment_status === 'PENDING_ADMIN_APPROVAL');

        if (pending.length === 0) {
            container.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:20px;">No cash payments pending verification.</td></tr>';
            return;
        }

        container.innerHTML = pending.map(p => `
            <tr>
                <td>#${p.id}</td>
                <td>User ID: ${p.user_id}</td>
                <td>Vehicle ID: ${p.vehicle_id}</td>
                <td>$${Number(p.amount).toLocaleString()}</td>
                <td>
                    <button onclick="verifyCash(${p.id})" class="btn-verify">
                        Confirm Cash Received
                    </button>
                </td>
            </tr>
        `).join('');
    } catch (error) {
        console.error("Error loading pending payments:", error);
    }
}

/**
 * Admin: Verify a specific cash payment
 */
async function verifyCash(purchaseId) {
    if (!confirm("Have you received the physical cash for this vehicle?")) return;

    try {
        const response = await fetch(`${API_BASE_URL}/admin/verify-purchase/${purchaseId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (response.ok) {
            alert("Payment Verified! Vehicle marked as SOLD.");
            loadPendingPayments(); // Refresh list
            if (window.loadAdminVehicles) loadAdminVehicles(); // Refresh inventory
        } else {
            alert("Verification failed.");
        }
    } catch (error) {
        alert("Server error.");
    }
}

/**
 * Customer: Load purchase history for the logged-in user
 */
async function loadUserPurchases() {
    const container = document.getElementById('purchasesContainer');
    if (!container || !currentUser) return;

    try {
        const response = await fetch(`${API_BASE_URL}/user/orders/${currentUser.id}`);
        const orders = await response.json();

        if (orders.length === 0) {
            container.innerHTML = '<div class="no-orders">No orders found yet. <a href="inventory.html">Browse Vehicles</a></div>';
            return;
        }

        container.innerHTML = orders.map(order => `
            <div class="order-card">
                <div class="order-header">
                    <div>
                        <h3>${order.vehicle}</h3>
                        <span class="order-id">Order #${order.id} • ${order.date}</span>
                    </div>
                    <span class="status-badge ${order.status === 'completed' ? 'status-success' : 'status-pending'}">
                        ${order.status.replace(/_/g, ' ')}
                    </span>
                </div>
                <div class="order-details">
                    <p>Method: ${order.method.toUpperCase()}</p>
                    <p class="order-price">$${Number(order.amount).toLocaleString()}</p>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error("Error loading purchases:", error);
        container.innerHTML = '<p>Error loading your orders.</p>';
    }
}

async function verifyCashPayment(purchaseId) {
    if (!confirm("Verify this cash payment? This will mark the vehicle as SOLD.")) return;

    try {
        const response = await fetch(`${API_BASE_URL}/admin/verify-purchase/${purchaseId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                user_id: currentUser.id // Crucial: Send admin ID for backend check
            })
        });

        const result = await response.json();
        if (response.ok) {
            alert("Success: " + result.message);
            // Re-load the list to remove the verified item
            if (window.loadPendingPayments) loadPendingPayments();
        } else {
            alert("Error: " + (result.error || "Verification failed"));
        }
    } catch (error) {
        console.error("Verification failed:", error);
        alert("Could not connect to server.");
    }
}

async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    const chatMessages = document.getElementById('chat-messages');

    if (!message) return;

    // Display user message
    chatMessages.innerHTML += `<div class="user-msg"><strong>You:</strong> ${message}</div>`;
    input.value = '';

    try {
        const response = await fetch(`${API_BASE_URL}/chatbot`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
        });
        
        const data = await response.json();
        
        // Display AI response
        chatMessages.innerHTML += `<div class="ai-msg"><strong>Bot:</strong> ${data.response}</div>`;
        chatMessages.scrollTop = chatMessages.scrollHeight; // Auto-scroll
    } catch (error) {
        console.error("Chat Error:", error);
    }
}

function toggleChat() {
    const window = document.getElementById('chat-window');
    window.classList.toggle('hidden');
}


//--- EXPORT FUNCTIONS FOR HTML ACCESS ---
window.handleLogin = handleLogin;
window.handleRegistration = handleRegistration;
window.handleLogout = handleLogout;
window.handleVehicleSearch = handleVehicleSearch;
window.handleAddVehicle = handleAddVehicle;
window.handleForgotPassword = handleForgotPassword;
window.handleResetPassword = handleResetPassword;
window.initiatePurchase = initiatePurchase;
window.viewVehicleDetails = viewVehicleDetails;
window.loadSalesReport = loadSalesReport;
window.loadCustomerInteractions = loadCustomerInteractions;
window.loadUserInsights = loadUserInsights;
window.addToCart = addToCart;
window.removeFromCart = removeFromCart;
window.checkout = checkout;
window.loadAvailableStock = loadAvailableStock;
window.applyReportFilters = applyReportFilters;
window.closeModal = closeModal;
window.deleteVehicle = deleteVehicle;
window.editVehicle = editVehicle;
window.displayCart = displayCart;
window.renderInventoryPage = renderInventoryPage;
window.loadPendingPayments = loadPendingPayments;
window.verifyCash = verifyCash;
window.loadUserPurchases = loadUserPurchases;
window.verifyCashPayment = verifyCashPayment;