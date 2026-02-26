// static/sw.js
// เพิ่มใน sw.js เพื่อ Debug บน Android
// static/sw.js
self.addEventListener('push', function(event) {
    console.log('[Service Worker] Push Received.');
    let data = { title: 'แจ้งเตือน', body: 'มีข้อความใหม่' };
    
    try {
        data = event.data.json();
    } catch (e) {
        console.warn('Push event but no JSON data');
    }

    // NOTE: update `icon` and `badge` to your hosted logo URL (Cloudinary or static).
    // If you host the logo under the app's static files, the path below will work.
    const options = {
        body: data.body,
        // Replace with your Cloudinary URL if you prefer an external CDN image.
        icon: '/static/img/mini-hrm-logo.png',
        badge: '/static/img/mini-hrm-logo.png',
        vibrate: [100, 50, 100],
        data: {
            dateOfArrival: Date.now(),
            primaryKey: '1'
        }
    };

    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});


