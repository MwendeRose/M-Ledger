// Global variables
let currentPage = 1;
const rowsPerPage = 5; // Show 5 transactions per page
let monthlyChart, categoryChart, yearlyChart;
let allTransactions = [];

// Theme Toggle
const themeToggle = document.getElementById('theme_toggle');
themeToggle.addEventListener('click', () => {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
});

// Load saved theme
window.addEventListener('DOMContentLoaded', () => {
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    
    // File input change
    document.getElementById('statement').addEventListener('change', function(e) {
        const fileName = e.target.files[0] ? e.target.files[0].name : 'Choose PDF File';
        document.getElementById('file_text').textContent = fileName;
    });
    
    // Load transactions from table
    loadTransactionsFromTable();
});

// Load transactions from table into memory
function loadTransactionsFromTable() {
    allTransactions = [];
    const rows = document.querySelectorAll('#transactions_tbody tr[data-category]');
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length >= 10) {
            const dateText = cells[1].textContent.trim().replace('📅', '').trim();
            const amountText = cells[7].textContent.trim().replace(/[+\-,\s]/g, '');
            const balanceText = cells[9].textContent.trim().replace(/[,\s]/g, '');
            
            const transaction = {
                date: dateText,
                time: cells[2].textContent.trim(),
                reference: cells[3].textContent.trim(),
                type: cells[4].textContent.trim(),
                party: cells[5].textContent.trim(),
                description: cells[6].textContent.trim(),
                amount: parseFloat(amountText) || 0,
                category: row.dataset.category,
                balance: parseFloat(balanceText) || 0
            };
            
            allTransactions.push(transaction);
        }
    });
    
    console.log('Loaded transactions:', allTransactions.length);
}

// Filter Toggle
document.getElementById('filter_toggle').addEventListener('click', function() {
    const filterControls = document.getElementById('filter_controls');
    const isHidden = filterControls.style.display === 'none';
    filterControls.style.display = isHidden ? 'block' : 'none';
    this.innerHTML = isHidden 
        ? '<svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M3 3a1 1 0 011-1h12a1 1 0 011 1v3a1 1 0 01-.293.707L12 11.414V15a1 1 0 01-.293.707l-2 2A1 1 0 018 17v-5.586L3.293 6.707A1 1 0 013 6V3z" clip-rule="evenodd"/></svg> Hide Filters' 
        : '<svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M3 3a1 1 0 011-1h12a1 1 0 011 1v3a1 1 0 01-.293.707L12 11.414V15a1 1 0 01-.293.707l-2 2A1 1 0 018 17v-5.586L3.293 6.707A1 1 0 013 6V3z" clip-rule="evenodd"/></svg> Show Filters';
});

// Upload Form
$('#upload_form').submit(function(e){
    e.preventDefault();
    
    const fileInput = $('#statement')[0];
    if (!fileInput.files[0]) {
        showNotification('Please select a PDF file', 'warning');
        return;
    }
    
    $('#upload_btn_text').text('Processing...');
    $('#upload_spinner').show();
    $('#upload_btn').prop('disabled', true);
    
    const formData = new FormData(this);
    
    $.ajax({
        url: '/',
        type: 'POST',
        data: formData,
        processData: false,
        contentType: false,
        success: function(response) {
            showNotification('✅ Statement processed! Reloading...', 'success');
            setTimeout(() => location.reload(), 1500);
        },
        error: function(xhr) {
            showNotification('❌ Upload failed: ' + xhr.responseText, 'error');
        },
        complete: function() {
            $('#upload_btn_text').text('Upload & Process');
            $('#upload_spinner').hide();
            $('#upload_btn').prop('disabled', false);
        }
    });
});

// Status Pills
document.querySelectorAll('.status-pill').forEach(pill => {
    pill.addEventListener('click', function() {
        document.querySelectorAll('.status-pill').forEach(p => p.classList.remove('active'));
        this.classList.add('active');
        
        // Reset to page 1 when changing filter
        currentPage = 1;
        updatePagination();
    });
});

// Pagination - Show only 5 transactions per page
function updatePagination() {
    const allRows = Array.from(document.querySelectorAll('#transactions_tbody tr[data-category]'));
    const activeStatus = document.querySelector('.status-pill.active');
    const status = activeStatus ? activeStatus.dataset.status : 'all';
    
    // Filter rows based on active status
    const visibleRows = allRows.filter(row => {
        if (status === 'all') return true;
        return row.dataset.category === status;
    });
    
    const totalPages = Math.ceil(visibleRows.length / rowsPerPage) || 1;
    
    // Ensure current page is within bounds
    if (currentPage > totalPages) {
        currentPage = totalPages;
    }
    if (currentPage < 1) {
        currentPage = 1;
    }
    
    // Calculate start and end indices for current page
    const startIndex = (currentPage - 1) * rowsPerPage;
    const endIndex = startIndex + rowsPerPage;
    
    // Hide all rows first
    allRows.forEach(row => {
        row.style.display = 'none';
    });
    
    // Show only the rows for the current page
    let displayedCount = 0;
    visibleRows.forEach((row, index) => {
        if (index >= startIndex && index < endIndex) {
            row.style.display = '';
            displayedCount++;
        }
    });
    
    // Update pagination display with "X of Y" format for each transaction
    const transactionNumber = startIndex + 1;
    const lastTransactionNumber = Math.min(endIndex, visibleRows.length);
    
    if (visibleRows.length === 0) {
        document.getElementById('page_info').textContent = `No transactions`;
    } else if (displayedCount === 1) {
        document.getElementById('page_info').textContent = `${transactionNumber} of ${visibleRows.length} transactions | Page ${currentPage} of ${totalPages}`;
    } else {
        document.getElementById('page_info').textContent = `${transactionNumber} - ${lastTransactionNumber} of ${visibleRows.length} transactions | Page ${currentPage} of ${totalPages}`;
    }
    
    document.getElementById('prev_page').disabled = currentPage <= 1;
    document.getElementById('next_page').disabled = currentPage >= totalPages;
    
    // Update button text
    const prevBtn = document.getElementById('prev_page');
    const nextBtn = document.getElementById('next_page');
    prevBtn.textContent = `← Previous`;
    nextBtn.textContent = `Next →`;
}

document.getElementById('prev_page').addEventListener('click', () => {
    if (currentPage > 1) {
        currentPage--; // Go back 1 page
        updatePagination();
        
        // Scroll to top of table
        document.querySelector('.table-container').scrollIntoView({ 
            behavior: 'smooth', 
            block: 'start' 
        });
    }
});

document.getElementById('next_page').addEventListener('click', () => {
    const allRows = Array.from(document.querySelectorAll('#transactions_tbody tr[data-category]'));
    const activeStatus = document.querySelector('.status-pill.active');
    const status = activeStatus ? activeStatus.dataset.status : 'all';
    
    const visibleRows = allRows.filter(row => {
        if (status === 'all') return true;
        return row.dataset.category === status;
    });
    
    const totalPages = Math.ceil(visibleRows.length / rowsPerPage) || 1;
    
    if (currentPage < totalPages) {
        currentPage++; // Go forward 1 page
        updatePagination();
        
        // Scroll to top of table
        document.querySelector('.table-container').scrollIntoView({ 
            behavior: 'smooth', 
            block: 'start' 
        });
    }
});

// Add keyboard navigation (optional enhancement)
document.addEventListener('keydown', (e) => {
    // Only if not typing in an input field
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        // Previous page
        const prevBtn = document.getElementById('prev_page');
        if (!prevBtn.disabled) {
            prevBtn.click();
        }
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        // Next page
        const nextBtn = document.getElementById('next_page');
        if (!nextBtn.disabled) {
            nextBtn.click();
        }
    }
});

function showNotification(message, type = 'info') {
    const statusDiv = document.getElementById('upload_status');
    const icon = type === 'success' ? '✅' : 
                 type === 'error' ? '❌' : 
                 type === 'warning' ? '⚠️' : 'ℹ️';
    
    statusDiv.innerHTML = `<div class="alert alert-${type}">${icon} ${message}</div>`;
    setTimeout(() => statusDiv.innerHTML = '', 5000);
}

function formatNumber(value) {
    return parseFloat(value).toLocaleString('en-US', { 
        minimumFractionDigits: 2, 
        maximumFractionDigits: 2 
    });
}

// Navigation
document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', function(e) {
        e.preventDefault();
        
        document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));
        this.classList.add('active');
        
        const section = this.dataset.section;
        
        document.querySelectorAll('.content-section').forEach(sec => sec.style.display = 'none');
        
        const targetSection = document.getElementById(`${section}-section`);
        if (targetSection) targetSection.style.display = 'block';
        
        const titles = {
            'home': 'Home',
            'reports': 'Reports',
            'settings': 'Settings'
        };
        
        document.getElementById('page_title').textContent = titles[section] || 'M-Ledger AI';
        
        const newExpenseBtn = document.getElementById('new_expense_btn');
        newExpenseBtn.style.display = section === 'home' ? 'inline-flex' : 'none';
    });
});

// Chat toggle - minimize/expand
const chatToggle = document.getElementById('chat_toggle');
const chatHeader = document.querySelector('.chat-header');
const chatMessages = document.getElementById('ai_chat_messages');
const chatForm = document.getElementById('ai_chat_form');

// Function to toggle chat
function toggleChat() {
    const isExpanded = chatMessages.classList.contains('expanded');
    
    if (isExpanded) {
        chatMessages.classList.remove('expanded');
        chatForm.classList.remove('expanded');
        chatToggle.style.transform = 'rotate(180deg)';
    } else {
        chatMessages.classList.add('expanded');
        chatForm.classList.add('expanded');
        chatToggle.style.transform = 'rotate(0deg)';
        
        // Scroll chat into view when opened
        setTimeout(() => {
            document.querySelector('.ai-chat-section').scrollIntoView({ 
                behavior: 'smooth', 
                block: 'nearest' 
            });
        }, 100);
    }
}

// Make header clickable
chatHeader.addEventListener('click', toggleChat);

chatToggle.addEventListener('click', function(e) {
    e.stopPropagation(); // Prevent double trigger
});

// Initialize chat as EXPANDED (visible by default)
chatMessages.classList.add('expanded');
chatForm.classList.add('expanded');
chatToggle.style.transform = 'rotate(0deg)';

// ===========================
// AI CHAT FUNCTIONALITY - ENHANCED
// ===========================

// AI Chat Form Submit
document.getElementById('ai_chat_form').addEventListener('submit', function(e) {
    e.preventDefault();
    
    const input = document.getElementById('ai_chat_input');
    const userMessage = input.value.trim();
    
    if (!userMessage) return;
    
    // Add user message to chat
    addMessageToChat('user', userMessage);
    
    // Clear input
    input.value = '';
    
    // Show typing indicator
    addTypingIndicator();
    
    // Get AI response
    getAIResponse(userMessage);
});

function addMessageToChat(sender, message) {
    const messagesContainer = document.getElementById('ai_chat_messages');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `ai-chat-message ${sender}`;
    
    const avatarDiv = document.createElement('div');
    avatarDiv.className = sender === 'user' ? 'user-avatar' : 'bot-avatar';
    avatarDiv.textContent = sender === 'user' ? '👤' : '🤖';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    // Preserve line breaks and formatting
    contentDiv.style.whiteSpace = 'pre-wrap';
    contentDiv.textContent = message;
    
    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(contentDiv);
    
    messagesContainer.appendChild(messageDiv);
    
    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function addTypingIndicator() {
    const messagesContainer = document.getElementById('ai_chat_messages');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'ai-chat-message bot typing-message';
    messageDiv.id = 'typing-indicator';
    
    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'bot-avatar';
    avatarDiv.textContent = '🤖';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div> Thinking...';
    
    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(contentDiv);
    
    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function removeTypingIndicator() {
    const typingIndicator = document.getElementById('typing-indicator');
    if (typingIndicator) {
        typingIndicator.remove();
    }
}

function getAIResponse(userMessage) {
    // Load transactions if not already loaded
    if (allTransactions.length === 0) {
        loadTransactionsFromTable();
    }
    
    // Simulate AI processing time
    setTimeout(() => {
        removeTypingIndicator();
        
        const response = generateAIResponse(userMessage);
        
        // If no response (empty string), show "No response"
        if (!response || response.trim() === "") {
            addMessageToChat('bot', 'No response.');
        } else {
            addMessageToChat('bot', response);
        }
    }, 1000 + Math.random() * 1000); // 1-2 seconds delay
}

// ===========================
// NEW: PERSON/BUSINESS SEARCH FUNCTIONS
// ===========================

/**
 * Find transactions involving a specific person or business
 * @param {string} searchTerm - Name of person or business to search for
 * @param {string} direction - 'sent', 'received', or 'all'
 * @returns {Array} - Array of matching transactions
 */
function findTransactionsByPerson(searchTerm, direction = 'all') {
    const term = searchTerm.toLowerCase().trim();
    
    return allTransactions.filter(t => {
        const party = (t.party || '').toLowerCase();
        const description = (t.description || '').toLowerCase();
        const type = (t.type || '').toLowerCase();
        const reference = (t.reference || '').toLowerCase();
        
        // Check if search term matches ANY field
        // Use includes for partial matching (e.g., "MSHWARI" matches "M-Shwari")
        const matchesSearch = party.includes(term) || 
                             description.includes(term) || 
                             type.includes(term) ||
                             reference.includes(term) ||
                             // Also try without hyphens/spaces
                             party.replace(/[\s\-]/g, '').includes(term.replace(/[\s\-]/g, '')) ||
                             description.replace(/[\s\-]/g, '').includes(term.replace(/[\s\-]/g, '')) ||
                             type.replace(/[\s\-]/g, '').includes(term.replace(/[\s\-]/g, ''));
        
        if (!matchesSearch) return false;
        
        // Filter by direction
        if (direction === 'sent') {
            return t.category === 'expense';
        } else if (direction === 'received') {
            return t.category === 'income';
        }
        
        return true; // 'all'
    });
}

/**
 * Extract person/business name from user query
 */
function extractPersonName(message) {
    const lowerMsg = message.toLowerCase();
    
    // Patterns to extract names (ordered by specificity)
    const patterns = [
        // "total amount received from X" or "total received from X"
        /(?:total\s+amount\s+(?:i\s+)?received\s+from|total\s+(?:i\s+)?received\s+from)\s+([a-z0-9\s\-\.]+?)(?:\s|$|\?)/i,
        // "total amount sent to X" or "total sent to X"
        /(?:total\s+amount\s+(?:i\s+)?sent\s+to|total\s+(?:i\s+)?sent\s+to|total\s+(?:i\s+)?paid\s+to)\s+([a-z0-9\s\-\.]+?)(?:\s|$|\?)/i,
        // Standard "sent to" patterns
        /(?:sent to|send to|paid to|pay to|transferred to|transfer to)\s+([a-z0-9\s\-\.]+?)(?:\s|$|\?)/i,
        // Standard "received from" patterns
        /(?:received from|got from|from)\s+([a-z0-9\s\-\.]+?)(?:\s|$|\?)/i,
        // "transactions with" patterns
        /(?:transactions with|transaction with|with)\s+([a-z0-9\s\-\.]+?)(?:\s|$|\?)/i,
    ];
    
    for (const pattern of patterns) {
        const match = message.match(pattern);
        if (match && match[1]) {
            return match[1].trim();
        }
    }
    
    return null;
}

/**
 * Determine transaction direction from query
 */
function getTransactionDirection(message) {
    const lowerMsg = message.toLowerCase();
    
    // Check for "received from" patterns (higher priority)
    if (lowerMsg.includes('received from') || lowerMsg.includes('got from')) {
        return 'received';
    }
    
    // Check for "sent to" / "paid to" patterns (higher priority)
    if (lowerMsg.includes('sent to') || lowerMsg.includes('paid to') || lowerMsg.includes('transferred to')) {
        return 'sent';
    }
    
    // General direction keywords
    if (lowerMsg.includes('sent') || lowerMsg.includes('paid') || lowerMsg.includes('transferred') || lowerMsg.includes('send')) {
        return 'sent';
    } else if (lowerMsg.includes('received') || lowerMsg.includes('got')) {
        return 'received';
    }
    
    return 'all';
}

function generateAIResponse(userMessage) {
    const message = userMessage.toLowerCase();
    
    // Check if transactions are available
    if (allTransactions.length === 0) {
        return "I don't see any transactions yet. Please upload an M-Pesa statement first, and I'll be able to help you analyze your finances!";
    }
    
    // Calculate financial data
    const financialData = calculateFinancialSummary();
    
    // ===========================
    // NEW: PERSON/BUSINESS QUERIES
    // ===========================
    
    // Check for person/business queries
    const personName = extractPersonName(userMessage);
    
    if (personName && (
        message.includes('sent to') || 
        message.includes('send to') ||
        message.includes('paid to') || 
        message.includes('received from') || 
        message.includes('got from') ||
        message.includes('transactions with') ||
        message.includes('transaction with') ||
        message.includes('how much') ||
        message.includes('total amount') ||
        message.includes('total') ||
        message.includes('highest') ||
        message.includes('largest') ||
        message.includes('biggest')
    )) {
        const direction = getTransactionDirection(userMessage);
        const transactions = findTransactionsByPerson(personName, direction);
        
        if (transactions.length > 0) {
            // Check if asking for HIGHEST amount
            if (message.includes('highest') || message.includes('largest') || message.includes('biggest')) {
                // Find the highest transaction
                let highest = transactions[0];
                transactions.forEach(txn => {
                    if (txn.amount > highest.amount) {
                        highest = txn;
                    }
                });
                
                const directionText = direction === 'sent' ? 'sent to' : 
                                    direction === 'received' ? 'received from' : 
                                    'with';
                
                let response = `Your highest amount ${directionText} ${personName} was KES ${formatNumber(highest.amount)} on ${highest.date}.\n\n`;
                response += `Date: ${highest.date} at ${highest.time}\n`;
                response += `Amount: KES ${formatNumber(highest.amount)}\n`;
                response += `Type: ${highest.type}\n`;
                if (highest.party && highest.party !== '-') {
                    response += `Party: ${highest.party}\n`;
                }
                response += `Description: ${highest.description}\n`;
                response += `Reference: ${highest.reference}\n`;
                response += `Balance after: KES ${formatNumber(highest.balance)}`;
                
                return response;
            }
            
            let totalAmount = 0;
            let directionText = direction === 'sent' ? 'sent to' : 
                              direction === 'received' ? 'received from' : 
                              'with';
            
            // Check if user is asking for just the total
            const isAskingTotal = message.includes('total amount') || 
                                 (message.includes('total') && !message.includes('show all'));
            
            if (isAskingTotal) {
                // Just show the total summary
                transactions.forEach(txn => totalAmount += txn.amount);
                
                let response = `You ${directionText} ${personName} a total of KES ${formatNumber(totalAmount)}`;
                response += ` across ${transactions.length} transaction${transactions.length > 1 ? 's' : ''}.`;
                
                return response;
            } else {
                // Show all transaction details
                let response = `Here are all transactions ${directionText} ${personName}:\n\n`;
                
                transactions.forEach((txn, index) => {
                    totalAmount += txn.amount;
                    
                    response += `${index + 1}. ${txn.date} at ${txn.time}\n`;
                    response += `   Amount: KES ${formatNumber(txn.amount)}\n`;
                    response += `   ${txn.description}\n`;
                    response += `   Balance after: KES ${formatNumber(txn.balance)}\n\n`;
                });
                
                response += `Total: KES ${formatNumber(totalAmount)} (${transactions.length} transaction${transactions.length > 1 ? 's' : ''})`;
                
                return response;
            }
        } else {
            // No matches found
            return `No transactions found ${directionText} ${personName}.`;
        }
    }
    
    // ===========================
    // EXISTING QUERIES (UNCHANGED)
    // ===========================
    
    // HIGHEST CATEGORY EXPENSE/INCOME (e.g., "highest mshwari expense", "highest mshwari income")
    if (message.includes('highest') || message.includes('largest') || message.includes('biggest')) {
        let categoryKeyword = '';
        let categoryName = '';
        
        if (message.includes('airtime')) {
            categoryKeyword = 'airtime';
            categoryName = 'Airtime';
        } else if (message.includes('withdraw')) {
            categoryKeyword = 'withdraw';
            categoryName = 'Withdrawals';
        } else if (message.includes('paybill') || message.includes('bill')) {
            categoryKeyword = 'paybill';
            categoryName = 'Bills & PayBill';
        } else if (message.includes('buy goods') || message.includes('shopping')) {
            categoryKeyword = 'buy goods';
            categoryName = 'Buy Goods / Shopping';
        } else if (message.includes('send money') || message.includes('transfer')) {
            categoryKeyword = 'send money';
            categoryName = 'Send Money / Transfers';
        } else if (message.includes('m-shwari') || message.includes('mshwari')) {
            categoryKeyword = 'm-shwari';
            categoryName = 'M-Shwari';
        }
        
        if (categoryKeyword) {
            let categoryTransactions = findTransactionsByCategory(categoryKeyword);
            
            // Filter by income or expense if specified
            if (message.includes('income')) {
                categoryTransactions = categoryTransactions.filter(t => t.category === 'income');
            } else if (message.includes('expense')) {
                categoryTransactions = categoryTransactions.filter(t => t.category === 'expense');
            }
            // If neither specified, show all (could be income or expense)
            
            if (categoryTransactions.length > 0) {
                // Find the highest transaction in this category
                let highest = categoryTransactions[0];
                categoryTransactions.forEach(txn => {
                    if (txn.amount > highest.amount) {
                        highest = txn;
                    }
                });
                
                const typeText = message.includes('income') ? 'income' : 
                                message.includes('expense') ? 'expense' : 'transaction';
                
                let response = `Your highest ${categoryName} ${typeText} was KES ${formatNumber(highest.amount)} on ${highest.date}.\n\n`;
                response += `Date: ${highest.date} at ${highest.time}\n`;
                response += `Amount: KES ${formatNumber(highest.amount)}\n`;
                response += `Type: ${highest.type}\n`;
                if (highest.party && highest.party !== '-') {
                    response += `Party: ${highest.party}\n`;
                }
                response += `Description: ${highest.description}\n`;
                response += `Reference: ${highest.reference}\n`;
                response += `Balance after: KES ${formatNumber(highest.balance)}`;
                
                return response;
            }
            
            const typeText = message.includes('income') ? 'income' : 
                            message.includes('expense') ? 'expense' : '';
            return `No ${categoryName} ${typeText} transactions found.`.trim();
        }
    }
    
    // CATEGORY-BASED SPENDING QUERIES (e.g., "how much on airtime")
    if (message.includes('how much') || message.includes('spent on') || message.includes('spending on')) {
        let categoryKeyword = '';
        let categoryName = '';
        
        if (message.includes('airtime')) {
            categoryKeyword = 'airtime';
            categoryName = 'Airtime';
        } else if (message.includes('withdraw')) {
            categoryKeyword = 'withdraw';
            categoryName = 'Withdrawals';
        } else if (message.includes('paybill') || message.includes('bill')) {
            categoryKeyword = 'paybill';
            categoryName = 'Bills & PayBill';
        } else if (message.includes('buy goods') || message.includes('shopping')) {
            categoryKeyword = 'buy goods';
            categoryName = 'Buy Goods / Shopping';
        } else if (message.includes('send money') || message.includes('transfer')) {
            categoryKeyword = 'send money';
            categoryName = 'Send Money / Transfers';
        } else if (message.includes('m-shwari') || message.includes('mshwari')) {
            categoryKeyword = 'm-shwari';
            categoryName = 'M-Shwari';
        }
        
        if (categoryKeyword) {
            const categoryTransactions = findTransactionsByCategory(categoryKeyword);
            if (categoryTransactions.length > 0) {
                let totalSum = 0;
                let response = `You spent KES `;
                
                categoryTransactions.forEach(txn => totalSum += txn.amount);
                
                response = `You spent KES ${formatNumber(totalSum)} on ${categoryName} (${categoryTransactions.length} transactions).\n\n`;
                
                categoryTransactions.forEach((txn, index) => {
                    response += `${index + 1}. ${txn.date} - KES ${formatNumber(txn.amount)}\n`;
                    response += `   ${txn.description}\n\n`;
                });
                
                return response;
            }
            return `No ${categoryName} transactions found.`;
        }
    }
    
    // TOTAL INCOME
    if (message.includes('total income') || (message.includes('income') && message.includes('total'))) {
        const incomeTransactions = allTransactions.filter(t => t.category === 'income');
        let totalSum = 0;
        incomeTransactions.forEach(t => totalSum += t.amount);
        
        return `Your total income is KES ${formatNumber(totalSum)} from ${incomeTransactions.length} transactions.`;
    }
    
    // TOTAL CHARGES
    if (message.includes('total charges') || message.includes('total charge') || (message.includes('charge') && message.includes('total'))) {
        const charges = findAllCharges();
        let totalSum = 0;
        charges.forEach(c => totalSum += c.amount);
        
        return `You paid KES ${formatNumber(totalSum)} in M-Pesa charges across ${charges.length} transactions.`;
    }
    
    // TOTAL EXPENSES
    if (message.includes('total expenses') || message.includes('total expense') || (message.includes('expense') && message.includes('total'))) {
        const expenseTransactions = allTransactions.filter(t => t.category === 'expense');
        let totalSum = 0;
        expenseTransactions.forEach(t => totalSum += t.amount);
        
        return `Your total expenses are KES ${formatNumber(totalSum)} from ${expenseTransactions.length} transactions.`;
    }
    
    // SHOW HIGHEST INCOME
    if (message.includes('highest income') || message.includes('largest income') || message.includes('biggest income')) {
        const highestIncome = findHighestIncome();
        if (highestIncome) {
            let response = `Your highest income was KES ${formatNumber(highestIncome.amount)} on ${highestIncome.date}.\n\n`;
            response += `Date: ${highestIncome.date} at ${highestIncome.time}\n`;
            response += `Amount: KES ${formatNumber(highestIncome.amount)}\n`;
            response += `Type: ${highestIncome.type}\n`;
            if (highestIncome.party && highestIncome.party !== '-') {
                response += `Party: ${highestIncome.party}\n`;
            }
            response += `Description: ${highestIncome.description}\n`;
            response += `Reference: ${highestIncome.reference}\n`;
            response += `Balance after: KES ${formatNumber(highestIncome.balance)}`;
            
            return response;
        }
        return "No income transactions found.";
    }
    
    // SHOW HIGHEST EXPENSE
    if (message.includes('highest expense') || message.includes('largest expense') || message.includes('biggest expense')) {
        const highestExpense = findHighestExpense();
        if (highestExpense) {
            let response = `Your highest expense was KES ${formatNumber(highestExpense.amount)} on ${highestExpense.date}.\n\n`;
            response += `Date: ${highestExpense.date} at ${highestExpense.time}\n`;
            response += `Amount: KES ${formatNumber(highestExpense.amount)}\n`;
            response += `Type: ${highestExpense.type}\n`;
            if (highestExpense.party && highestExpense.party !== '-') {
                response += `Party: ${highestExpense.party}\n`;
            }
            response += `Description: ${highestExpense.description}\n`;
            response += `Reference: ${highestExpense.reference}\n`;
            response += `Balance after: KES ${formatNumber(highestExpense.balance)}`;
            
            return response;
        }
        return "No expense transactions found.";
    }
    
    // SHOW HIGHEST CHARGE
    if (message.includes('highest charge') || message.includes('largest charge') || message.includes('biggest charge')) {
        const highestCharge = findHighestCharge();
        if (highestCharge) {
            let response = `Your highest charge was KES ${formatNumber(highestCharge.amount)} on ${highestCharge.date}.\n\n`;
            response += `Date: ${highestCharge.date} at ${highestCharge.time}\n`;
            response += `Amount: KES ${formatNumber(highestCharge.amount)}\n`;
            response += `Type: ${highestCharge.type}\n`;
            response += `Description: ${highestCharge.description}\n`;
            response += `Reference: ${highestCharge.reference}\n`;
            response += `Balance after: KES ${formatNumber(highestCharge.balance)}`;
            
            return response;
        }
        return "No charge transactions found.";
    }
    
    // SHOW RECENT TRANSACTIONS
    if (message.includes('recent transactions') || message.includes('latest transactions') || message.includes('last 5')) {
        const recent = getRecentTransactions(5);
        if (recent.length > 0) {
            let response = `Here are your recent transactions:\n\n`;
            recent.forEach((txn, index) => {
                response += `${index + 1}. ${txn.date} - KES ${formatNumber(txn.amount)}\n`;
                response += `   ${txn.description}\n\n`;
            });
            return response;
        }
        return "No recent transactions found.";
    }
    
    // TOP 5 EXPENSES
    if (message.includes('top 5 expenses') || message.includes('highest 5 expenses') || message.includes('top expenses')) {
        const topExpenses = findTopExpenses(5);
        if (topExpenses.length > 0) {
            let totalSum = 0;
            topExpenses.forEach(exp => totalSum += exp.amount);
            
            let response = `Your top ${topExpenses.length} expenses (Total: KES ${formatNumber(totalSum)}):\n\n`;
            topExpenses.forEach((exp, index) => {
                response += `${index + 1}. ${exp.date} - KES ${formatNumber(exp.amount)}\n`;
                response += `   ${exp.description}\n\n`;
            });
            return response;
        }
        return "No expense transactions found.";
    }
    
    // TOP 5 INCOME
    if (message.includes('top 5 income') || message.includes('highest 5 income') || message.includes('top income')) {
        const topIncome = findTopIncome(5);
        if (topIncome.length > 0) {
            let totalSum = 0;
            topIncome.forEach(inc => totalSum += inc.amount);
            
            let response = `Your top ${topIncome.length} income sources (Total: KES ${formatNumber(totalSum)}):\n\n`;
            topIncome.forEach((inc, index) => {
                response += `${index + 1}. ${inc.date} - KES ${formatNumber(inc.amount)}\n`;
                response += `   ${inc.description}\n\n`;
            });
            return response;
        }
        return "No income transactions found.";
    }
    
    // BALANCE SUMMARY
    if (message.includes('balance') || message.includes('summary') || message.includes('overview')) {
        let response = `Here's your financial summary:\n\n`;
        response += `Income: KES ${formatNumber(financialData.totalIncome)} (${financialData.incomeCount} transactions)\n`;
        response += `Expenses: KES ${formatNumber(financialData.totalExpenses)} (${financialData.expenseCount} transactions)\n`;
        response += `Charges: KES ${formatNumber(financialData.totalCharges)} (${financialData.chargeCount} transactions)\n\n`;
        response += `Net: KES ${formatNumber(financialData.netBalance)}`;
        
        if (financialData.netBalance > 0) {
            response += ` - You're in the positive!`;
        }
        
        return response;
    }
    
    // TRANSACTION COUNT
    if (message.includes('how many') || message.includes('count')) {
        return `You have ${allTransactions.length} total transactions:\n` +
               `Income: ${financialData.incomeCount}\n` +
               `Expenses: ${financialData.expenseCount}\n` +
               `Charges: ${financialData.chargeCount}`;
    }
    
    // LARGEST TRANSACTION
    if (message.includes('biggest') || message.includes('largest')) {
        const largest = findLargestTransaction();
        let response = `Your largest transaction was KES ${formatNumber(largest.amount)} on ${largest.date}.\n\n`;
        response += `Date: ${largest.date} at ${largest.time}\n`;
        response += `Amount: KES ${formatNumber(largest.amount)}\n`;
        response += `Type: ${largest.type}\n`;
        if (largest.party && largest.party !== '-') {
            response += `Party: ${largest.party}\n`;
        }
        response += `Description: ${largest.description}\n`;
        response += `Reference: ${largest.reference}\n`;
        response += `Balance after: KES ${formatNumber(largest.balance)}`;
        
        return response;
    }
    
    // HELP
    if (message.includes('help') || message.includes('what can you do')) {
        return `I can help you with:\n\n` +
               `• "Total received from NCBA" or "Total sent to Safaricom"\n` +
               `• "Highest from M-Shwari" or "Highest to John"\n` +
               `• "Highest M-Shwari expense" or "Highest M-Shwari income"\n` +
               `• "Highest airtime" or "Highest withdrawal"\n` +
               `• "Total income", "Total expenses", "Total charges"\n` +
               `• "Highest income" or "Highest expense"\n` +
               `• "How much spent on airtime"\n` +
               `• "Top 5 expenses"\n` +
               `• "Recent transactions"\n` +
               `• "Summary" or "Balance"\n\n` +
               `Just ask naturally!`;
    }
    
    // NO DEFAULT RESPONSE - Return nothing if no pattern matches
    return "";
}

function calculateFinancialSummary() {
    let totalIncome = 0;
    let totalExpenses = 0;
    let totalCharges = 0;
    let incomeCount = 0;
    let expenseCount = 0;
    let chargeCount = 0;
    
    const categories = {};
    
    allTransactions.forEach(t => {
        if (t.category === 'income') {
            totalIncome += t.amount;
            incomeCount++;
        } else if (t.category === 'expense') {
            totalExpenses += t.amount;
            expenseCount++;
            
            // Categorize expenses
            const desc = (t.description || '').toLowerCase();
            const type = (t.type || '').toLowerCase();
            
            let category = 'Other';
            if (desc.includes('airtime') || type.includes('airtime')) {
                category = 'Airtime';
            } else if (desc.includes('withdraw')) {
                category = 'Withdrawals';
            } else if (desc.includes('paybill')) {
                category = 'Bills';
            } else if (desc.includes('buy goods')) {
                category = 'Shopping';
            } else if (desc.includes('send money')) {
                category = 'Transfers';
            }
            
            categories[category] = (categories[category] || 0) + t.amount;
        } else if (t.category === 'charge') {
            totalCharges += t.amount;
            chargeCount++;
        }
    });
    
    // Find top category
    let topCategory = 'None';
    let topCategoryAmount = 0;
    
    Object.entries(categories).forEach(([cat, amount]) => {
        if (amount > topCategoryAmount) {
            topCategory = cat;
            topCategoryAmount = amount;
        }
    });
    
    return {
        totalIncome,
        totalExpenses,
        totalCharges,
        netBalance: totalIncome - totalExpenses - totalCharges,
        incomeCount,
        expenseCount,
        chargeCount,
        topCategory,
        topCategoryAmount
    };
}

function findLargestTransaction() {
    if (allTransactions.length === 0) {
        return { type: 'None', amount: 0, date: 'N/A', time: 'N/A', description: 'No transactions', reference: 'N/A', party: 'N/A' };
    }
    
    let largest = allTransactions[0];
    
    allTransactions.forEach(t => {
        if (t.amount > largest.amount) {
            largest = t;
        }
    });
    
    return {
        type: largest.category,
        amount: largest.amount,
        date: largest.date,
        time: largest.time,
        description: largest.description,
        reference: largest.reference,
        party: largest.party,
        category: largest.category,
        balance: largest.balance
    };
}

// Find highest income transaction
function findHighestIncome() {
    const incomeTransactions = allTransactions.filter(t => t.category === 'income');
    if (incomeTransactions.length === 0) return null;
    
    let highest = incomeTransactions[0];
    incomeTransactions.forEach(t => {
        if (t.amount > highest.amount) {
            highest = t;
        }
    });
    
    return highest;
}

// Find highest expense transaction
function findHighestExpense() {
    const expenseTransactions = allTransactions.filter(t => t.category === 'expense');
    if (expenseTransactions.length === 0) return null;
    
    let highest = expenseTransactions[0];
    expenseTransactions.forEach(t => {
        if (t.amount > highest.amount) {
            highest = t;
        }
    });
    
    return highest;
}

// Find all charge transactions
function findAllCharges() {
    return allTransactions.filter(t => t.category === 'charge');
}

// Get recent transactions
function getRecentTransactions(count = 5) {
    return allTransactions.slice(0, count);
}

// Find highest charge transaction
function findHighestCharge() {
    const chargeTransactions = allTransactions.filter(t => t.category === 'charge');
    if (chargeTransactions.length === 0) return null;
    
    let highest = chargeTransactions[0];
    chargeTransactions.forEach(t => {
        if (t.amount > highest.amount) {
            highest = t;
        }
    });
    
    return highest;
}

// Find transactions by category keyword
function findTransactionsByCategory(keyword) {
    return allTransactions.filter(t => {
        const desc = (t.description || '').toLowerCase();
        const type = (t.type || '').toLowerCase();
        return desc.includes(keyword) || type.includes(keyword);
    });
}

// Find top N expenses
function findTopExpenses(count = 5) {
    const expenses = allTransactions.filter(t => t.category === 'expense');
    return expenses.sort((a, b) => b.amount - a.amount).slice(0, count);
}

// Find top N income
function findTopIncome(count = 5) {
    const income = allTransactions.filter(t => t.category === 'income');
    return income.sort((a, b) => b.amount - a.amount).slice(0, count);
}

// REPORTS - Calculate from table data
document.querySelectorAll('.report-btn').forEach(btn => {
    btn.addEventListener('click', function() {
        const reportType = this.dataset.report;
        
        loadTransactionsFromTable();
        
        if (allTransactions.length === 0) {
            showNotification('⚠️ No transactions. Upload a statement first.', 'warning');
            return;
        }
        
        document.querySelector('.report-cards').style.display = 'none';
        document.querySelector('.reports-grid > h2').style.display = 'none';
        document.getElementById(`${reportType}-report`).style.display = 'block';
        
        if (reportType === 'monthly') {
            updateMonthlyReport(calculateMonthlyData());
        } else if (reportType === 'category') {
            updateCategoryReport(calculateCategoryData());
        } else if (reportType === 'yearly') {
            updateYearlyReport(calculateYearlyData());
        }
        
        showNotification('✅ Report generated', 'success');
    });
});

document.querySelectorAll('.back-to-reports').forEach(btn => {
    btn.addEventListener('click', function() {
        document.querySelectorAll('.report-detail').forEach(d => d.style.display = 'none');
        document.querySelector('.report-cards').style.display = 'grid';
        document.querySelector('.reports-grid > h2').style.display = 'block';
    });
});

function calculateMonthlyData() {
    const now = new Date();
    const currentMonth = now.getMonth() + 1;
    const currentYear = now.getFullYear();
    
    let totalIncome = 0, totalExpenses = 0;
    
    allTransactions.forEach(t => {
        const parts = t.date.split('-');
        if (parts.length === 3) {
            const txYear = parseInt(parts[0]);
            const txMonth = parseInt(parts[1]);
            
            if (txYear === currentYear && txMonth === currentMonth) {
                if (t.category === 'income') {
                    totalIncome += t.amount;
                } else if (t.category === 'expense' || t.category === 'charge') {
                    totalExpenses += t.amount;
                }
            }
        }
    });
    
    console.log('Monthly:', { totalIncome, totalExpenses });
    return { total_income: totalIncome, total_expenses: totalExpenses };
}

function calculateCategoryData() {
    const categories = {
        'Airtime': 0,
        'M-Shwari': 0,
        'Withdrawals': 0,
        'Bills & Utilities': 0,
        'Shopping': 0,
        'Send Money': 0,
        'Other': 0
    };
    
    let totalExpenses = 0;
    
    allTransactions.forEach(t => {
        if (t.category === 'expense' || t.category === 'charge') {
            totalExpenses += t.amount;
            
            const desc = (t.description || '').toLowerCase();
            const type = (t.type || '').toLowerCase();
            
            if (desc.includes('airtime') || type.includes('airtime')) {
                categories['Airtime'] += t.amount;
            } else if (desc.includes('m-shwari') || type.includes('m-shwari')) {
                categories['M-Shwari'] += t.amount;
            } else if (desc.includes('withdraw') || type.includes('withdraw')) {
                categories['Withdrawals'] += t.amount;
            } else if (desc.includes('paybill') || desc.includes('pay bill')) {
                categories['Bills & Utilities'] += t.amount;
            } else if (desc.includes('buy goods')) {
                categories['Shopping'] += t.amount;
            } else if (desc.includes('send money') || desc.includes('sent to')) {
                categories['Send Money'] += t.amount;
            } else {
                categories['Other'] += t.amount;
            }
        }
    });
    
    const categoryArray = Object.entries(categories)
        .map(([name, amount]) => ({ name, amount }))
        .filter(cat => cat.amount > 0)
        .sort((a, b) => b.amount - a.amount);
    
    console.log('Categories:', categoryArray);
    return { total_expenses: totalExpenses, categories: categoryArray };
}

function calculateYearlyData() {
    const currentYear = new Date().getFullYear();
    let totalIncome = 0, totalExpenses = 0;
    const monthlyTotals = {};
    
    allTransactions.forEach(t => {
        const parts = t.date.split('-');
        if (parts.length === 3) {
            const txYear = parseInt(parts[0]);
            const txMonth = parseInt(parts[1]);
            
            if (txYear === currentYear) {
                const key = `${txYear}-${txMonth}`;
                if (!monthlyTotals[key]) monthlyTotals[key] = { income: 0, expenses: 0 };
                
                if (t.category === 'income') {
                    totalIncome += t.amount;
                    monthlyTotals[key].income += t.amount;
                } else if (t.category === 'expense' || t.category === 'charge') {
                    totalExpenses += t.amount;
                    monthlyTotals[key].expenses += t.amount;
                }
            }
        }
    });
    
    const monthCount = Object.keys(monthlyTotals).length || 1;
    const monthlyAverage = (totalIncome + totalExpenses) / monthCount;
    
    console.log('Yearly:', { totalIncome, totalExpenses, monthlyAverage });
    return { 
        total_income: totalIncome, 
        total_expenses: totalExpenses,
        monthly_average: monthlyAverage
    };
}

function updateMonthlyReport(data) {
    const income = data.total_income || 0;
    const expenses = data.total_expenses || 0;
    const net = income - expenses;
    
    document.getElementById('monthly_income').textContent = `KES ${formatNumber(income)}`;
    document.getElementById('monthly_expenses').textContent = `KES ${formatNumber(expenses)}`;
    document.getElementById('monthly_net').textContent = `KES ${formatNumber(net)}`;
    
    if (monthlyChart) monthlyChart.destroy();
    
    const ctx = document.getElementById('monthly-chart').getContext('2d');
    monthlyChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Income', 'Expenses', 'Net'],
            datasets: [{
                data: [income, expenses, net],
                backgroundColor: [
                    'rgba(16, 185, 129, 0.85)', // Green for income
                    'rgba(239, 68, 68, 0.85)', // Red for expenses
                    'rgba(124, 58, 237, 0.85)' // Purple for net
                ],
                borderColor: [
                    'rgb(16, 185, 129)',
                    'rgb(239, 68, 68)',
                    'rgb(124, 58, 237)'
                ],
                borderWidth: 2,
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
                title: {
                    display: true,
                    text: 'Monthly Financial Overview',
                    font: { size: 18, weight: 'bold' },
                    color: '#1e293b',
                    padding: 20
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(0, 0, 0, 0.05)' },
                    ticks: { color: '#475569' }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#475569' }
                }
            }
        }
    });
}

function updateCategoryReport(data) {
    const list = document.getElementById('category_breakdown');
    list.innerHTML = '';
    
    if (data.categories && data.categories.length > 0) {
        data.categories.forEach(cat => {
            const pct = ((cat.amount / data.total_expenses) * 100).toFixed(1);
            list.innerHTML += `
                <div class="category-item">
                    <div class="category-header">
                        <span class="category-name">${cat.name}</span>
                        <span class="category-amount">KES ${formatNumber(cat.amount)}</span>
                    </div>
                    <div class="category-bar">
                        <div class="category-progress" style="width: ${pct}%"></div>
                    </div>
                    <div class="category-percentage">${pct}% of total</div>
                </div>
            `;
        });
        
        if (categoryChart) categoryChart.destroy();
        
        const ctx = document.getElementById('category-chart').getContext('2d');
        
        const categoryColors = [
            'rgba(124, 58, 237, 0.85)', // Purple
            'rgba(16, 185, 129, 0.85)', // Green
            'rgba(239, 68, 68, 0.85)', // Red
            'rgba(245, 158, 11, 0.85)', // Orange
            'rgba(59, 130, 246, 0.85)', // Blue
            'rgba(236, 72, 153, 0.85)', // Pink
            'rgba(20, 184, 166, 0.85)' // Teal
        ];
        
        categoryChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: data.categories.map(c => c.name),
                datasets: [{
                    data: data.categories.map(c => c.amount),
                    backgroundColor: categoryColors.slice(0, data.categories.length),
                    borderWidth: 3,
                    borderColor: '#ffffff',
                    hoverOffset: 8
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 20,
                            font: { size: 13 },
                            color: '#1e293b',
                            usePointStyle: true,
                            pointStyle: 'circle'
                        }
                    },
                    title: {
                        display: true,
                        text: 'Expense Distribution by Category',
                        font: { size: 18, weight: 'bold' },
                        color: '#1e293b',
                        padding: 20
                    }
                }
            }
        });
    } else {
        list.innerHTML = '<div class="empty-state"><div class="empty-text">No data</div></div>';
    }
}

function updateYearlyReport(data) {
    const income = data.total_income || 0;
    const expenses = data.total_expenses || 0;
    const average = data.monthly_average || 0;
    
    document.getElementById('yearly_income').textContent = `KES ${formatNumber(income)}`;
    document.getElementById('yearly_expenses').textContent = `KES ${formatNumber(expenses)}`;
    document.getElementById('yearly_average').textContent = `KES ${formatNumber(average)}`;
    
    if (yearlyChart) yearlyChart.destroy();
    
    const ctx = document.getElementById('yearly-chart').getContext('2d');
    yearlyChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
            datasets: [
                {
                    label: 'Income',
                    data: Array(12).fill(income/12),
                    borderColor: 'rgb(16, 185, 129)',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    tension: 0.4,
                    fill: true,
                    borderWidth: 3,
                    pointRadius: 6,
                    pointBackgroundColor: 'rgb(16, 185, 129)',
                    pointBorderColor: '#fff',
                    pointBorderWidth: 2,
                    pointHoverRadius: 8
                },
                {
                    label: 'Expenses',
                    data: Array(12).fill(expenses/12),
                    borderColor: 'rgb(239, 68, 68)',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    tension: 0.4,
                    fill: true,
                    borderWidth: 3,
                    pointRadius: 6,
                    pointBackgroundColor: 'rgb(239, 68, 68)',
                    pointBorderColor: '#fff',
                    pointBorderWidth: 2,
                    pointHoverRadius: 8
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        padding: 20,
                        font: { size: 14, weight: 'bold' },
                        color: '#1e293b',
                        usePointStyle: true,
                        pointStyle: 'circle'
                    }
                },
                title: {
                    display: true,
                    text: 'Annual Financial Trend',
                    font: { size: 18, weight: 'bold' },
                    color: '#1e293b',
                    padding: 20
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(0, 0, 0, 0.05)' },
                    ticks: { color: '#475569' }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#475569' }
                }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            }
        }
    });
}

$(document).ready(function() {
    updatePagination();
    loadTransactionsFromTable();
});