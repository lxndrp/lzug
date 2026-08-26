/* global self, fetch, clients */

self.addEventListener('push', (event) => {
  event.waitUntil(
    (async () => {
      try {
        const response = await fetch('/api/notifications', { credentials: 'include' });
        if (response.ok) {
          const collection = await response.json();
          await Promise.all(
            (collection.items || []).map((item) =>
              fetch(`/api/notifications/${item.id}/push-confirmation`, {
                method: 'POST',
                credentials: 'include',
              }),
            ),
          );
        }
      } finally {
        await self.registration.showNotification('Neue Benachrichtigung in lzug', {
          body: 'Öffnen Sie lzug, um die geschützten Details anzusehen.',
          tag: 'lzug-notification',
          data: { url: '/notifications' },
        });
      }
    })(),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(clients.openWindow(event.notification.data.url));
});
