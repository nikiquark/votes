/**
 * Django Messages to Toastify Integration
 * 
 * Отображает сообщения Django через Toastify с прогресс-баром.
 * Сообщения показываются в нижнем правом углу с разумными отступами.
 */

(function () {
    'use strict';

    // Конфигурация
    const CONFIG = {
        // Длительность отображения уведомления (мс)
        duration: 5000,
        // Отступы от краев экрана (px)
        offset: {
            bottom: 20,
            right: 20
        },
        // Маппинг тегов Django на стили Toastify
        tagStyles: {
            'success': {
                background: '#28a745'
            },
            'error': {
                background: '#dc3545'
            },
            'warning': {
                background: '#ffc107'
            },
            'info': {
                background: '#17a2b8'
            },
            'debug': {
                background: '#6c757d'
            }
        },
        // Минимальная ширина уведомления
        minWidth: 300,
        // Максимальная ширина уведомления
        maxWidth: 500
    };

    /**
     * Нормализует тег сообщения Django
     * Django может использовать комбинации тегов, например "error" или "messages.error"
     */
    function normalizeTag(tag) {
        if (!tag) return 'info';
        
        // Убираем префикс "messages." если есть
        const cleanTag = tag.replace(/^messages\./, '');
        
        // Проверяем наличие тега в конфигурации
        if (CONFIG.tagStyles.hasOwnProperty(cleanTag)) {
            return cleanTag;
        }
        
        // Fallback на info
        return 'info';
    }

    /**
     * Создает элемент прогресс-бара с поддержкой паузы при наведении
     */
    function createProgressBar(duration, wrapper) {
        const progressBar = document.createElement('div');
        progressBar.className = 'toast-progress-bar';
        
        // Используем CSS animation для возможности паузы
        const animationName = `toast-progress-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        
        // Создаем keyframes для анимации
        const styleSheet = document.createElement('style');
        styleSheet.textContent = `
            @keyframes ${animationName} {
                from {
                    transform: scaleX(1);
                }
                to {
                    transform: scaleX(0);
                }
            }
        `;
        document.head.appendChild(styleSheet);
        
        // Настраиваем анимацию
        progressBar.style.animation = `${animationName} ${duration}ms linear forwards`;
        progressBar.style.animationPlayState = 'running';
        
        // Обработчики для паузы/возобновления при наведении
        wrapper.addEventListener('mouseenter', () => {
            progressBar.style.animationPlayState = 'paused';
        });
        
        wrapper.addEventListener('mouseleave', () => {
            progressBar.style.animationPlayState = 'running';
        });
        
        return progressBar;
    }

    /**
     * Отображает одно сообщение через Toastify
     */
    function showMessage(text, tag) {
        const normalizedTag = normalizeTag(tag);
        const style = CONFIG.tagStyles[normalizedTag];
        
        // Создаем обертку для сообщения с прогресс-баром
        const messageWrapper = document.createElement('div');
        messageWrapper.className = 'django-toast';
        messageWrapper.style.position = 'relative';
        messageWrapper.style.overflow = 'hidden';
        
        // Создаем контент сообщения с текстом
        const messageContent = document.createElement('div');
        messageContent.textContent = text;
        messageWrapper.appendChild(messageContent);
        
        // Добавляем прогресс-бар (передаем wrapper для обработчиков событий)
        const progressBar = createProgressBar(CONFIG.duration, messageWrapper);
        messageWrapper.appendChild(progressBar);
        
        // Настраиваем стили прогресс-бара в зависимости от типа сообщения
        if (normalizedTag === 'success' || normalizedTag === 'info') {
            progressBar.style.backgroundColor = 'rgba(255, 255, 255, 0.5)';
        } else {
            progressBar.style.backgroundColor = 'rgba(0, 0, 0, 0.3)';
        }
        
        // Отображаем через Toastify
        const toast = Toastify({
            node: messageWrapper,
            duration: CONFIG.duration,
            gravity: 'bottom',
            position: 'right',
            style: {
                background: style.background,
                color: '#ffffff',
                padding: '0',
                borderRadius: '0.375rem',
                boxShadow: '0 0.125rem 0.25rem rgba(0, 0, 0, 0.075), 0 0.5rem 1rem rgba(0, 0, 0, 0.15)',
                minWidth: `${CONFIG.minWidth}px`,
                maxWidth: `${CONFIG.maxWidth}px`,
                marginBottom: `${CONFIG.offset.bottom}px`,
                marginRight: `${CONFIG.offset.right}px`
            },
            offset: {
                x: CONFIG.offset.right,
                y: CONFIG.offset.bottom
            },
            close: false, // Не показываем крестик
            stopOnFocus: true // Останавливает таймер при наведении
        });
        
        toast.showToast();
        
        // Добавляем курсор pointer для индикации кликабельности
        messageWrapper.style.cursor = 'pointer';
        
        // Добавляем обработчик клика напрямую на элемент toast после его создания
        setTimeout(() => {
            const toastElement = toast.toastElement;
            if (toastElement) {
                // Обработчик клика на весь элемент toast
                toastElement.addEventListener('click', function(e) {
                    e.stopPropagation();
                    this.remove();
                });
                // Также добавляем курсор на сам элемент toast
                toastElement.style.cursor = 'pointer';
                
                // Также добавляем обработчик на messageWrapper для надежности
                messageWrapper.addEventListener('click', function(e) {
                    e.stopPropagation();
                    toastElement.remove();
                });
            }
        }, 0);
    }

    /**
     * Инициализация: обработка сообщений Django при загрузке страницы
     */
    function init() {
        // Ждем полной загрузки DOM
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', processMessages);
        } else {
            processMessages();
        }
    }

    /**
     * Обрабатывает все сообщения Django из скрытого контейнера
     */
    function processMessages() {
        const messagesContainer = document.querySelector('[data-django-messages]');
        
        if (!messagesContainer) {
            return;
        }
        
        const messageElements = messagesContainer.querySelectorAll('[data-message]');
        
        if (messageElements.length === 0) {
            return;
        }
        
        // Обрабатываем каждое сообщение с небольшой задержкой для визуального эффекта
        messageElements.forEach((element, index) => {
            const text = element.textContent.trim();
            const tag = element.getAttribute('data-message-tag') || 'info';
            
            if (!text) {
                return;
            }
            
            // Небольшая задержка между сообщениями для лучшего UX
            setTimeout(() => {
                showMessage(text, tag);
            }, index * 100);
        });
        
        // Удаляем контейнер после обработки
        messagesContainer.remove();
    }

    /**
     * Отображает сообщение об ошибке API с предложением перезагрузить страницу
     */
    function showApiError(message) {
        const errorMessage = message || 'Произошла ошибка при обращении к серверу. Пожалуйста, перезагрузите страницу.';
        showMessage(errorMessage, 'error');
    }

    // Запускаем инициализацию
    init();

    // Экспортируем функцию для программного использования (опционально)
    if (typeof window !== 'undefined') {
        window.djangoMessages = {
            show: showMessage,
            showApiError: showApiError,
            config: CONFIG
        };
    }
})();
