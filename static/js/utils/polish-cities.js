/**
 * Polish Cities Lat/Lng Lookup Table
 * Used for shipment tracking map (Leaflet) to place delivery markers
 * without requiring a geocoding API.
 */

window.POLISH_CITIES = {
    'warszawa':                  [52.2297, 21.0122],
    'kraków':                    [50.0647, 19.9450],
    'łódź':                      [51.7592, 19.4560],
    'wrocław':                   [51.1079, 17.0385],
    'poznań':                    [52.4064, 16.9252],
    'gdańsk':                    [54.3520, 18.6466],
    'szczecin':                  [53.4289, 14.5530],
    'bydgoszcz':                 [53.1235, 18.0084],
    'lublin':                    [51.2465, 22.5684],
    'białystok':                 [53.1325, 23.1688],
    'katowice':                  [50.2649, 19.0238],
    'gdynia':                    [54.5189, 18.5305],
    'częstochowa':               [50.8118, 19.1203],
    'radom':                     [51.4027, 21.1471],
    'toruń':                     [53.0138, 18.5981],
    'sosnowiec':                 [50.2863, 19.1041],
    'rzeszów':                   [50.0412, 21.9991],
    'kielce':                    [50.8661, 20.6286],
    'gliwice':                   [50.2945, 18.6714],
    'olsztyn':                   [53.7784, 20.4801],
    'zabrze':                    [50.3249, 18.7857],
    'bielsko-biała':             [49.8225, 19.0444],
    'bytom':                     [50.3483, 18.9170],
    'zielona góra':              [51.9356, 15.5062],
    'rybnik':                    [50.1025, 18.5462],
    'ruda śląska':               [50.2591, 18.8560],
    'opole':                     [50.6751, 17.9213],
    'tychy':                     [50.1357, 18.9968],
    'gorzów wielkopolski':       [52.7368, 15.2288],
    'elbląg':                    [54.1522, 19.4088],
    'płock':                     [52.5463, 19.7065],
    'dąbrowa górnicza':          [50.3231, 19.1837],
    'wałbrzych':                 [50.7714, 16.2843],
    'włocławek':                 [52.6483, 19.0678],
    'tarnów':                    [50.0121, 20.9858],
    'chorzów':                   [50.2977, 18.9523],
    'koszalin':                  [54.1943, 16.1724],
    'kalisz':                    [51.7611, 18.0910],
    'legnica':                   [51.2070, 16.1619],
    'grudziądz':                 [53.4837, 18.7536],
    'jaworzno':                  [50.2053, 19.2741],
    'słupsk':                    [54.4641, 17.0285],
    'jastrzębie-zdrój':          [49.9575, 18.5748],
    'nowy sącz':                 [49.6249, 20.6983],
    'jelenia góra':              [50.9044, 15.7197],
    'siedlce':                   [52.1676, 22.2902],
    'mysłowice':                 [50.2234, 19.1666],
    'konin':                     [52.2230, 18.2511],
    'piła':                      [53.1513, 16.7386],
    'piotrków trybunalski':      [51.4047, 19.6979],
    'inowrocław':                [52.7981, 18.2600],
    'lubin':                     [51.4011, 16.2003],
    'ostrów wielkopolski':       [51.6510, 17.8219],
    'suwałki':                   [54.1115, 22.9307],
    'stargard':                  [53.3376, 15.0510],
    'gniezno':                   [52.5350, 17.5956],
    'ostrowiec świętokrzyski':   [50.9297, 21.3885],
    'siemianowice śląskie':      [50.3232, 19.0257],
    'głogów':                    [51.6644, 16.0820],
    'pabianice':                 [51.6633, 19.3528],
    'leszno':                    [51.8404, 16.5755],
    'zamość':                    [50.7230, 23.2520],
    'łomża':                     [53.1781, 22.0593],
    'racławówka':                [49.85,   22.15  ],
};

/**
 * Look up coordinates for a Polish city name.
 * @param {string} cityName - City name (any case, with or without Polish characters)
 * @returns {[number, number]} [lat, lng] array, or center of Poland as fallback
 */
window.lookupCityCoords = function(cityName) {
    if (!cityName) return [51.9194, 19.1451];
    var key = cityName.toLowerCase().trim();
    return window.POLISH_CITIES[key] || [51.9194, 19.1451];
};
