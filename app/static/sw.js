// static/sw.js
// เพิ่มใน sw.js เพื่อ Debug บน Android
self.addEventListener('push', function(event) {
    console.log('[Service Worker] Push Received.');
    let data = { title: 'แจ้งเตือน', body: 'มีข้อความใหม่' };
    
    try {
        data = event.data.json();
    } catch (e) {
        console.warn('Push event but no JSON data');
    }

    const options = {
        body: data.body,
        icon: '/static/img/mini-hrm-logo.png',
        badge: '/static/img/mini-hrm-logo.png',
        vibrate: [100, 50, 100], // Android รองรับการสั่น
        data: {
            dateOfArrival: Date.now(),
            primaryKey: '1'
        }
    };

    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

// เมื่อกดที่แจ้งเตือน ให้เปิดหน้าเว็บรายงาน
self.addEventListener('notificationclick', e => {
    e.notification.close();
    e.waitUntil(clients.openWindow('/attendance-report'));
});
