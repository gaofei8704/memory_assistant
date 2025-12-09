// 基础JavaScript功能
document.addEventListener('DOMContentLoaded', function() {
    console.log('记忆助手应用已加载');

    // 初始化工具提示等通用功能
    initTooltips();
});

function initTooltips() {
    // 这里可以初始化工具提示等通用UI功能
    console.log('初始化UI组件');
}

// 通用模态框功能
function showModal(modalId) {
    document.getElementById(modalId).style.display = 'block';
}

function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

// 通用消息提示
function showMessage(message, type = 'info') {
    // 创建消息元素
    const messageEl = document.createElement('div');
    messageEl.className = `message message-${type}`;
    messageEl.textContent = message;

    // 添加到页面
    document.body.appendChild(messageEl);

    // 自动消失
    setTimeout(() => {
        messageEl.remove();
    }, 3000);
}

// 添加消息样式
const style = document.createElement('style');
style.textContent = `
    .message {
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        border-radius: 6px;
        color: white;
        z-index: 10000;
        animation: slideIn 0.3s ease-out;
    }
    
    .message-info {
        background-color: #3498db;
    }
    
    .message-success {
        background-color: #27ae60;
    }
    
    .message-error {
        background-color: #e74c3c;
    }
    
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
`;
document.head.appendChild(style);