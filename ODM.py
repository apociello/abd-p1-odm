__author__ = 'Pablo Ramos Criado'
__students__ = 'Javier Cejuela, Asier Pociello'


from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import time
from typing import Generator, Any, Self
from geojson import Point
import pymongo
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from bson.objectid import ObjectId
import yaml

def getLocationPoint(address: str) -> Point:
    """ 
    Obtiene las coordenadas de una dirección en formato geojson.Point
    Utilizar la API de geopy para obtener las coordenadas de la direccion
    Cuidado, la API es publica tiene limite de peticiones, utilizar sleeps.

    Parameters
    ----------
        address : str
            direccion completa de la que obtener las coordenadas
    Returns
    -------
        geojson.Point
            coordenadas del punto de la direccion
    """
    location = None
    intentos = 0
    maxIntentos = 5

    while location is None and intentos < maxIntentos:
        intentos += 1
        try:
            time.sleep(1)
            #TODO
            # Es necesario proporcionar un user_agent para utilizar la API
            # Utilizar un nombre aleatorio para el user_agent
            location = Nominatim(user_agent="Mi-Nombre-Aleatorio").geocode(address)
        except GeocoderTimedOut:
            # Puede lanzar una excepcion si se supera el tiempo de espera
            # Volver a intentarlo
            continue
    #TODO
    # Devolver un GeoJSON de tipo punto con la latitud y longitud almacenadas.
    # Si no se consiguieron coordenadas, lanzar ValueError: la funcion no puede
    # devolver un punto inventado ni None silenciosamente. Es lo que espera la
    # prueba test_get_location_point_timeout_failure.
    if location is None:
        raise ValueError("No se pudieron obtener coordenadas")

    return Point((location.longitude, location.latitude))

class Model:
    """ 
    Clase de modelo abstracta
    Crear tantas clases que hereden de esta clase como  
    colecciones/modelos se deseen tener en la base de datos.

    Attributes
    ----------
        required_vars : set[str]
            conjunto de atributos requeridos por el modelo
        admissible_vars : set[str]
            conjunto de atributos admitidos por el modelo
        db : pymongo.collection.Collection
            conexion a la coleccion de la base de datos
    
    Methods
    -------
        __setattr__(name: str, value: str | dict) -> None
            Sobreescribe el metodo de asignacion de valores a los 
            atributos del objeto con el fin de controlar qué atributos 
            son modificados y cuando son modificados.
        __getattr__(name: str) -> Any
            Sobreescribe el metodo de acceso a atributos del objeto 
        save()  -> None
            Guarda el modelo en la base de datos
        delete() -> None
            Elimina el modelo de la base de datos
        find(filter: dict[str, str | dict]) -> ModelCursor
            Realiza una consulta de lectura en la BBDD.
            Devuelve un cursor de modelos ModelCursor
        aggregate(pipeline: list[dict]) -> pymongo.command_cursor.CommandCursor
            Devuelve el resultado de una consulta aggregate.
        find_by_id(id: str) -> dict | None
            Busca un documento por su id utilizando la cache y lo devuelve.
            Si no se encuentra el documento, devuelve None.
        init_class(db_collection: pymongo.collection.Collection, required_vars: set[str], admissible_vars: set[str]) -> None
            Inicializa las variables de clase en la inicializacion del sistema.

    """
    _required_vars: set[str]
    _admissible_vars: set[str]
    _location_var: str | None = None
    _db: pymongo.collection.Collection
    _internal_vars: set[str] = frozenset(('_modified_vars', '_required_vars', '_admissible_vars', '_db', '_data', '_location_var'))

    def __init__(self, **kwargs: dict[str, str | dict | list]) -> None:
        """
        Inicializa el modelo con los valores proporcionados en kwargs
        Comprueba que los valores proporcionados en kwargs son admitidos
        por el modelo y que las atributos requeridos son proporcionadas.

        Parameters
        ----------
            kwargs : dict[str, str | dict]
                diccionario con los valores de las atributos del modelo
        """
        self._data: dict[str, str | dict | list] = {}
        self._modified_vars: set[str] = set()

        #TODO
        # Realizar las comprabociones y gestiones necesarias
        # antes de la asignacion.

        # Asigna todos los valores en kwargs a las atributos con 
        # nombre las claves en kwargs
        # Utilizamos el atributo data para guardar los variables 
        # almacenadas en la base de datos en una solo atributo
        # Encapsular los datos en una sola variable facilita la 
        # gestion en metodos como save.

        # Check required fields
        if not self._required_vars.issubset(kwargs.keys()):
            raise ValueError("Missing required fields")

        # Check allowed fields
        allowed_vars = self._required_vars | self._admissible_vars | {"_id"}

        if not set(kwargs.keys()).issubset(allowed_vars):
            raise ValueError("Unallowed fields present")

        self._data.update(kwargs)

    def __setattr__(self, name: str, value: str | dict) -> None:
        """ Sobreescribe el metodo de asignacion de valores a los 
        atributos del objeto con el fin de controlar que atributos 
        son modificados y cuando son modificados.
        """
        if name in self._internal_vars:
            super().__setattr__(name, value)
            return
        #TODO
        # Realizar las comprabociones y gestiones necesarias
        # antes de la asignacion.

        allowed_vars = self._required_vars | self._admissible_vars

        if name not in allowed_vars:
            raise ValueError("Unallowed field")

        # Asigna el valor value a la variable name
        self._data[name] = value
        self._modified_vars.add(name)

    def __getattr__(self, name: str) -> Any:
        """ Sobreescribe el metodo de acceso a atributos del objeto
        __getattr__ solo es llamado cuando no encuentra el atributo
        en el objeto 
        """
        if name in self._internal_vars:
            return super().__getattribute__(name)
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError
        
    def save(self) -> None:
        """
        Guarda el modelo en la base de datos
        Si el modelo no existe en la base de datos, se crea un nuevo
        documento con los valores del modelo. En caso contrario, se
        actualiza el documento existente con los nuevos valores del
        modelo.
        """
        #TODO
        if self._location_var and self._location_var in self._data:
            loc_field = f"{self._location_var}_loc"
            if loc_field not in self._data or self._location_var in self._modified_vars:
                self._data[loc_field] = getLocationPoint(self._data[self._location_var])
                self._modified_vars.add(loc_field)

        if "_id" not in self._data:
            result = self._db.insert_one(self._data)
            self._data["_id"] = result.inserted_id
        elif self._modified_vars:
            changes = {
                field: self._data[field]
                for field in self._modified_vars
            }

            self._db.update_one(
                {"_id": self._data["_id"]},
                {"$set": changes}
            )

        
        self._modified_vars.clear()

    def delete(self) -> None:
        """
        Elimina el modelo de la base de datos
        """
        #TODO
        if "_id" in self._data:
            self._db.delete_one({"_id": self._data["_id"]})
    
    @classmethod
    def find(cls, filter: dict[str, str | dict]) -> Any:
        """ 
        Utiliza el metodo find de pymongo para realizar una consulta
        de lectura en la BBDD.
        find debe devolver un cursor de modelos ModelCursor

        Parameters
        ----------
            filter : dict[str, str | dict]
                diccionario con el criterio de busqueda de la consulta
        Returns
        -------
            ModelCursor
                cursor de modelos
        """ 
        #TODO
        # cls es el puntero a la clase
        cursor = cls._db.find(filter)
        return ModelCursor(cls, cursor)

    @classmethod
    def aggregate(cls, pipeline: list[dict]) -> pymongo.command_cursor.CommandCursor:
        """ 
        Devuelve el resultado de una consulta aggregate. 
        No hay nada que hacer en esta funcion.
        Se utilizara para las consultas solicitadas
        en el segundo proyecto de la practica.

        Parameters
        ----------
            pipeline : list[dict]
                lista de etapas de la consulta aggregate 
        Returns
        -------
            pymongo.command_cursor.CommandCursor
                cursor de pymongo con el resultado de la consulta
        """ 
        return cls._db.aggregate(pipeline)
    
    @classmethod
    def find_by_id(cls, id: str) -> Self | None:
        """ 
        NO IMPLEMENTAR HASTA EL TERCER PROYECTO
        Busca un documento por su id utilizando la cache y lo devuelve.
        Si no se encuentra el documento, devuelve None.

        Parameters
        ----------
            id : str
                id del documento a buscar
        Returns
        -------
            Self | None
                Modelo del documento encontrado o None si no se encuentra
        """ 
        #TODO
        pass

    @classmethod
    def init_class(cls, db_collection: pymongo.collection.Collection, indexes:dict[str,str], required_vars: set[str], admissible_vars: set[str]) -> None:
        """ 
        Inicializa los atributos de clase en la inicializacion del sistema.
        Aqui se deben inicializar o asegurar los indices. Tambien se puede
        alguna otra inicialización/comprobaciones o cambios adicionales
        que estime el alumno.

        Parameters
        ----------
            db_collection : pymongo.collection.Collection
                Conexion a la collecion de la base de datos.
            indexes: Dict[str,str]
                Set de indices y tipo de indices para la coleccion
            required_vars : set[str]
                Set de atributos requeridos por el modelo
            admissible_vars : set[str] 
                Set de atributos admitidos por el modelo
        """
        cls._db = db_collection
        cls._required_vars = required_vars
        cls._admissible_vars = admissible_vars

        # TODO
        # Recorrer indexes y crear cada índice segun su tipo: 'unique', 'asc'
        # y 'geosphere'. Comparar el tipo por igualdad, no con el operador 'in'.
        # Ojo con el índice geoespacial: save() guarda el GeoJSON Point en
        # <campo>_loc, luego el índice 2dsphere va sobre <campo>_loc, mientras
        # que _location_var debe guardar el nombre del campo base.

        for field, index_type in indexes.items():

            if index_type == "unique":
                cls._db.create_index(field, unique=True)

            elif index_type == "asc":
                cls._db.create_index(field)

            elif index_type == "geosphere":
                cls._db.create_index([(field, "2dsphere")])
                cls._location_var = field.removesuffix("_loc")


class ModelCursor:
    """ 
    Cursor para iterar sobre los documentos del resultado de una
    consulta. Los documentos deben ser devueltos en forma de objetos
    modelo.

    Attributes
    ----------
        model_class : Model
            Clase para crear los modelos de los documentos que se iteran.
        cursor : pymongo.cursor.Cursor
            Cursor de pymongo a iterar

    Methods
    -------
        __iter__() -> Generator
            Devuelve un iterador que recorre los elementos del cursor
            y devuelve los documentos en forma de objetos modelo.
    """

    def __init__(self, model_class: Model, cursor: pymongo.cursor.Cursor):
        """
        Inicializa el cursor con la clase de modelo y el cursor de pymongo

        Parameters
        ----------
            model_class : Model
                Clase para crear los modelos de los documentos que se iteran.
            cursor: pymongo.cursor.Cursor
                Cursor de pymongo a iterar
        """
        self.model = model_class
        self.cursor = cursor
    
    def __iter__(self) -> Generator:
        """
        Devuelve un iterador que recorre los elementos del cursor
        y devuelve los documentos en forma de objetos modelo.
        Utilizar yield para generar el iterador
        Utilizar la funcion next para obtener el siguiente documento del cursor
        Utilizar alive para comprobar si existen mas documentos.
        """
        #TODO
        while self.cursor.alive:
            doc = self.cursor.next()
            yield self.model(**doc)


def initApp(definitions_path: str = "./models.yml", mongodb_uri="mongodb://localhost:27017/", db_name="abd", scope=globals()) -> None:
    """ 
    Declara las clases que heredan de Model para cada uno de los 
    modelos de las colecciones definidas en definitions_path.
    Inicializa las clases de los modelos proporcionando los indices y 
    atributos admitidos y requeridos para cada una de ellas y la conexión a la
    collecion de la base de datos.
    
    Parameters
    ----------
        definitions_path : str
            ruta al fichero de definiciones de modelos
        mongodb_uri : str
            uri de conexion a la base de datos
        db_name : str
            nombre de la base de datos
    """
    #TODO
    # Inicializar base de datos
    client = MongoClient(mongodb_uri)
    db = client[db_name]

    #TODO
    # Declarar tantas clases modelo colecciones existan en la base de datos
    # Leer el fichero de definiciones de modelos para obtener las colecciones,
    # indices y los atributos admitidos y requeridos para cada una de ellas.

    with open(definitions_path, "r") as file:
        definitions = yaml.safe_load(file)

    for model_name, definition in definitions.items():

        # Declare model class dynamically
        scope[model_name] = type(model_name, (Model,), {})

        required_vars = set(definition.get("required_vars", []))
        admissible_vars = set(definition.get("admissible_vars", []))

        indexes = {}

        for field in definition.get("unique_indexes", []):
            indexes[field] = "unique"

        for field in definition.get("regular_indexes", []):
            indexes[field] = "asc"

        if "location_index" in definition:
            location_field = definition["location_index"]
            indexes[f"{location_field}_loc"] = "geosphere"
            admissible_vars.add(f"{location_field}_loc")

        # The class is declared at runtime and remains in scope, which does not
        # have to be the global namespace: tests provide their own dictionary.
        scope[model_name].init_class(
            db_collection=db[model_name],
            indexes=indexes,
            required_vars=required_vars,
            admissible_vars=admissible_vars
        )
        

    # Ejemplo de declaracion de modelo para colecion llamada MiModelo
    #scope["MiModelo"] = type("MiModelo", (Model,),{})
    # La clase se declara en tiempo de ejecucion y queda en scope, que no tiene
    # por que ser el espacio de nombres global: las pruebas le pasan su propio
    # diccionario. Por eso se inicializa a traves de scope y no por su nombre,
    # que ahi todavia no existe.
    #scope["MiModelo"].init_class(db_collection=None, indexes=None, required_vars=None, admissible_vars=None)
    
if __name__ == '__main__':
    
    # Inicializar base de datos y modelos con initApp
    #TODO
    initApp()

    # Hacer pruebas para comprobar que funciona correctamente el modelo
    #TODO

    # --- Artists ---
    # Crear modelo
    artists_data = [
        {"name": "Rosalía", "music_genres": ["flamenco", "pop"],
         "country_origin": "Spain", "start_year": 2017},
        {"name": "Bad Bunny", "music_genres": ["reggaeton", "trap"],
         "country_origin": "Puerto Rico", "start_year": 2016},
        {"name": "Arctic Monkeys", "music_genres": ["indie rock"],
         "country_origin": "United Kingdom", "start_year": 2002},
        {"name": "Dua Lipa", "music_genres": ["pop"],
         "country_origin": "United Kingdom", "start_year": 2015},
        {"name": "Karol G", "music_genres": ["reggaeton", "pop"],
         "country_origin": "Colombia", "start_year": 2012},
    ]

    # Guardar
    artists = []
    for data in artists_data:
        artist = Artist(**data)
        artist.save()
        artists.append(artist)
        print("Artist created:", artist.name)

    # --- Venues ---
    # Crear modelo
    venues_data = [
        {"name": "Palau Sant Jordi", "address": "Passeig Olímpic, 5-7, Barcelona",
         "capacity": 17960, "services": ["parking", "accessibility"]},
        {"name": "WiZink Center", "address": "Av. Felipe II, s/n, Madrid",
         "capacity": 15500, "services": ["parking", "bar"]},
        {"name": "The O2 Arena", "address": "Peninsula Square, London",
         "capacity": 20000, "services": ["parking", "restaurants"]},
        {"name": "Movistar Arena", "address": "Av. Beazley 3860, Buenos Aires",
         "capacity": 15000, "services": ["parking", "bar"]},
    ]

    # Guardar
    venues = []
    for data in venues_data:
        venue = Venue(**data)
        venue.save()
        venues.append(venue)
        print("Venue created:", venue.name, "-", venue.address_loc)

    # --- Events ---
    # Crear modelo
    events_data = [
        {"title": "Motomami Tour - Barcelona", "artists": [artists[0].name],
         "venue": venues[0].name, "date_time": "2024-05-10T21:00:00",
         "price_area": {"Floor": 80, "Lower stand": 60}, "tickets_sold": 15200},
        {"title": "World's Hottest Tour - Madrid", "artists": [artists[1].name],
         "venue": venues[1].name, "date_time": "2023-11-03T20:30:00",
         "price_area": {"Floor": 90, "Amphitheater": 55}, "tickets_sold": 15500},
        {"title": "AM Anniversary - Buenos Aires", "artists": [artists[2].name],
         "venue": venues[3].name, "date_time": "2025-03-15T21:30:00",
         "price_area": {"Field": 70, "Stands": 50}, "tickets_sold": 13800},
        {"title": "Future Nostalgia Live - London", "artists": [artists[3].name],
         "venue": venues[2].name, "date_time": "2022-09-20T20:00:00",
         "price_area": {"Floor": 85, "Lower tier": 65}, "tickets_sold": 19000},
        {"title": "Urban Summer - Madrid", "artists": [artists[4].name, artists[0].name],
         "venue": venues[1].name, "date_time": "2025-07-12T22:00:00",
         "price_area": {"Floor": 75, "Amphitheater": 50}, "tickets_sold": 14900},
    ]

    # Guardar
    events = []
    for data in events_data:
        event = Event(**data)
        event.save()
        events.append(event)
        print("Event created:", event.title)

    # --- Attendees ---
    # Crear modelo
    attendees_data = [
        {"name": "Juan Pérez", "email": "juan.perez@gmail.com",
         "registration_date": "2023-01-15",
         "address": "Calle Mayor 1, Madrid",
         "genre_preferences": ["pop", "reggaeton"]},
        {"name": "Laura Gómez", "email": "laura.gomez@gmail.com",
         "registration_date": "2023-03-22",
         "address": "Carrer de Balmes 10, Barcelona",
         "genre_preferences": ["flamenco", "indie rock"]},
        {"name": "Carlos Ruiz", "email": "carlos.ruiz@gmail.com",
         "registration_date": "2024-02-10",
         "genre_preferences": ["trap"]},
        {"name": "Ana Torres", "email": "ana.torres@gmail.com",
         "registration_date": "2024-06-05",
         "genre_preferences": ["pop"]},
        {"name": "Marco Silva", "email": "marco.silva@gmail.com",
         "registration_date": "2025-01-30",
         "address": "Av. Beazley 3800, Buenos Aires",
         "genre_preferences": ["indie rock", "pop"]},
    ]

    # Guardar
    attendees = []
    for data in attendees_data:
        attendee = Attendee(**data)
        attendee.save()
        attendees.append(attendee)
        print("Attendee created:", attendee.name)

    print("\nAll EnVivo data created successfully.")
    