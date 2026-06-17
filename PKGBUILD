# Maintainer: esfingex (https://github.com/esfingex)
pkgname=thatch-git
pkgver=1.0.0.r0.g8ba2633
pkgrel=1
pkgdesc="Native, ultra-lightweight Wine Prefix & Compatibility Commander"
arch=('any')
url="https://github.com/esfingex/thatch"
license=('GPL3')
depends=('python' 'pyside6' 'winetricks' 'wine')
makedepends=('git' 'python-setuptools')
provides=('thatch')
conflicts=('thatch')
source=("git+https://github.com/esfingex/thatch.git")
sha256sums=('SKIP')

pkgver() {
  cd "$srcdir/thatch"
  git describe --long --tags | sed 's/\([^-]*-g\)/r\1/;s/-/./g'
}

package() {
  cd "$srcdir/thatch"
  # Instalar archivos del programa en /usr/share/thatch
  install -d "$pkgdir/usr/share/thatch"
  cp -r src config thatch.py "$pkgdir/usr/share/thatch/"

  # Crear un ejecutable lanzador en /usr/bin
  install -d "$pkgdir/usr/bin"
  cat <<EOF > "$pkgdir/usr/bin/thatch"
#!/bin/bash
exec python /usr/share/thatch/thatch.py "\$@"
EOF
  chmod +x "$pkgdir/usr/bin/thatch"

  # Instalar la Licencia
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE" 2>/dev/null || true
}
