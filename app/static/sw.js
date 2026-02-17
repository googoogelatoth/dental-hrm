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

    const options = {
        body: data.body,
        // ✨ แก้ตรงนี้: ใช้ลิงก์ Cloudinary ของโลโก้บริษัทนาย
        icon: 'https://res.cloudinary.com/your_cloud_name/image/upload/v12345/hrm/company/company_logo.png',
        badge: 'https://res.cloudinary.com/your_cloud_name/image/upload/v12345/hrm/company/company_logo.png',
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


