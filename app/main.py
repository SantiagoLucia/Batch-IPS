from pathlib import Path
import logging
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.types import Integer, String
from zeep import Client, Settings
import requests
import configparser
from tqdm import tqdm

config = configparser.ConfigParser()
config.read(Path("config.ini"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    filename=Path("logs/proceso.log").absolute(),
)


def get_token() -> str:
    response = requests.post(
        url=config["APP"]["URL_TOKEN"],
        auth=(
            config["APP"]["USUARIO_TOKEN"],
            config["APP"]["PASS_TOKEN"],
        ),
    )
    response.raise_for_status()
    if response.content.decode("utf-8") == "{No se pudo obtener el nombre de usuario}":
        raise requests.exceptions.HTTPError(
            f"401 Client Error: Unauthorized for url: {config['APP']['URL_TOKEN']}"
        )
    return response.content.decode("utf-8")


client_pase = Client(
    wsdl=config["APP"]["WSDL_PASE_EXPEDIENTE"], settings=Settings(strict=False)
)
client_bloqueo = Client(
    wsdl=config["APP"]["WSDL_BLOQUEO_EXPEDIENTE"], settings=Settings(strict=False)
)


def generar_pase(
    token: str,
    expediente: str,
    estado: str,
    usuario: str,
    reparticion_destino: str,
    sector_destino: str,
):
    client_pase.settings.extra_http_headers = {"Authorization": "Bearer " + token}
    request = {
        "datosPase": {
            "numeroExpediente": expediente,
            "esMesaDestino": False,
            "esReparticionDestino": False,
            "esSectorDestino": True,
            "esUsuarioDestino": False,
            "estadoSeleccionado": estado,
            "motivoPase": config["APP"]["MOTIVO_PASE"],
            "reparticionDestino": reparticion_destino,
            "sectorDestino": sector_destino,
            "usuarioOrigen": usuario,
        }
    }
    response = client_pase.service.generarPaseExpedienteConDesbloqueo(**request)
    return response


def bloquear(token: str, expediente: str):
    client_bloqueo.settings.extra_http_headers = {"Authorization": "Bearer " + token}
    request = expediente
    response = client_bloqueo.service.bloquearExpediente(request)
    return response


class Base(DeclarativeBase):
    pass


class Pase(Base):
    __tablename__ = "Pase"

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, nullable=False)
    expediente: Mapped[str] = mapped_column(String(100), nullable=False)
    estado_expediente: Mapped[str] = mapped_column(String(100), nullable=False)
    usuario_origen: Mapped[str] = mapped_column(String(100), nullable=False)
    reparticion_destino: Mapped[str] = mapped_column(String(100), nullable=False)
    sector_destino: Mapped[str] = mapped_column(String(100), nullable=False)
    estado_pase: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return (
            f"Pase(id={self.id!r}, "
            f"expediente={self.expediente!r}, "
            f"estado={self.estado_pase!r})"
        )


def main() -> None:
    db_path = Path("database/data.db").absolute()

    engine = create_engine(rf"sqlite:///{db_path}")
    session = Session(engine)
    select_stmt = (
        select(
            Pase.id,
            Pase.expediente,
            Pase.estado_expediente,
            Pase.usuario_origen,
            Pase.reparticion_destino,
            Pase.sector_destino,
        )
        .where(Pase.estado_pase == "pendiente")
        .limit(config["APP"]["CANTIDAD_PASES"])
    )

    resultado_select = session.execute(select_stmt).all()
    total_filas = len(resultado_select)

    if total_filas == 0:
        print("No hay pases en estado pendiente.")
        return

    for pase in tqdm(
        iterable=resultado_select,
        total=total_filas,
        desc="PROCESO",
    ):
        id, num_exp, estado_exp, usuario_origen, rep_dest, sec_dest = pase

        try:
            if estado_exp == "Paralelo":
                raise Exception(
                    f"{num_exp}: El expediente se encuentra en proceso de Tramitación en Paralelo"
                )

            nuevo_token = get_token()

            bloquear(token=nuevo_token, expediente=num_exp)
            resultado_pase = generar_pase(
                token=nuevo_token,
                expediente=num_exp,
                estado=estado_exp,
                usuario=usuario_origen,
                reparticion_destino=rep_dest,
                sector_destino=sec_dest,
            )
            estado_pase = "realizado"
            logging.info(resultado_pase)

        except Exception as e:
            estado_pase = "error"
            mensaje = str(e).split(".")[0]
            logging.error(f"{num_exp}: {mensaje}")

        finally:
            update_stmt = (
                update(Pase).where(Pase.id == id).values({"estado_pase": estado_pase})
            )
            session.execute(update_stmt)
            session.commit()


if __name__ == "__main__":
    main()
