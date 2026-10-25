// Light, warm Google map: beige land, white roads, soft green parks, no POI or transit icons.
export const MAP_STYLE = [
  { elementType: 'geometry', stylers: [{ color: '#F2EEE4' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#7A7262' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#F2EEE4' }, { weight: 3 }] },
  { featureType: 'administrative', elementType: 'geometry', stylers: [{ visibility: 'off' }] },
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
  { featureType: 'poi.park', elementType: 'geometry', stylers: [{ visibility: 'on' }, { color: '#DCE8CC' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#FFFFFF' }] },
  { featureType: 'road', elementType: 'geometry.stroke', stylers: [{ color: '#E9E1CD' }] },
  { featureType: 'road', elementType: 'labels.icon', stylers: [{ visibility: 'off' }] },
  { featureType: 'road.highway', elementType: 'geometry', stylers: [{ color: '#FFFDF6' }] },
  { featureType: 'transit', stylers: [{ visibility: 'off' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#CFE2E6' }] },
]
