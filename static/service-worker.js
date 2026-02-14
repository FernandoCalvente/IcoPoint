self.addEventListener('install', function(event) {
  console.log('Service Worker instalado');
});

self.addEventListener('fetch', function(event) {
  // Esto permite que la app siga funcionando offline para requests simples
});
