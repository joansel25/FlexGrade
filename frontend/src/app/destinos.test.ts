/**
 * Pruebas de la lista de destinos.
 *
 * Este archivo existe por una razón concreta: la barra de navegación y los accesos de la
 * pantalla de inicio divergieron DOS veces cuando eran dos listas separadas. Al añadir
 * «Expediente» solo se tocó la barra, y —más grave— los accesos de inicio nunca filtraron por
 * rol, así que un administrador veía las cinco pantallas del estudiante.
 *
 * Unificarlas cierra esa puerta. Lo que se comprueba aquí es el contrato de la lista única: que
 * cada destino declare quién lo ve, y que el filtro por rol no deje pasar nada ajeno.
 */

import { describe, expect, it } from "vitest";

import { DESTINOS, destinosDe } from "@/app/destinos";

describe("destinos de la aplicación", () => {
  it("cada destino dice a qué ruta lleva y cómo se llama en los dos sitios", () => {
    // La barra pinta `etiqueta` y la pantalla de inicio `titulo` y `descripcion`. Un destino al
    // que le falte uno de los tres se ve roto en uno de los dos sitios y entero en el otro, que
    // es la forma más fácil de no enterarse.
    for (const destino of DESTINOS) {
      expect(destino.a).toMatch(/^\//);
      expect(destino.etiqueta.length).toBeGreaterThan(0);
      expect(destino.titulo.length).toBeGreaterThan(0);
      expect(destino.descripcion.length).toBeGreaterThan(0);
    }
  });

  it("a un estudiante no le llega nada de administración ni de docencia", () => {
    const rutas = destinosDe("STUDENT").map((d) => d.a);

    expect(rutas).not.toContain("/admin");
    expect(rutas).not.toContain("/docencia");
  });

  it("a un administrador no le llega ninguna pantalla del estudiante", () => {
    // Todas responden `STUDENT_PROFILE_NOT_FOUND` a quien no lo es: ofrecerlas lleva a un error
    // que parece del sistema y es del menú.
    const rutas = destinosDe("ADMIN").map((d) => d.a);

    expect(rutas).toEqual(["/", "/admin"]);
  });

  it("a un docente solo le llegan sus grupos", () => {
    expect(destinosDe("PROFESSOR").map((d) => d.a)).toEqual(["/", "/docencia"]);
  });

  it("sin rol resuelto solo se pinta lo que no depende de él", () => {
    // Es la ventana entre el refresco de la sesión y su respuesta. Pintar enlaces de rol ahí y
    // retirarlos medio segundo después se lee como un parpadeo.
    expect(destinosDe(null).map((d) => d.a)).toEqual(["/"]);
  });

  it("ningún destino se declara para todos los roles a la vez", () => {
    // `roles: []` significa «siempre», y es lo correcto para Inicio. Enumerar los tres roles
    // significa lo mismo pero se rompe al añadir un rol nuevo: el destino dejaría de verse sin
    // que nadie lo tocara.
    for (const destino of DESTINOS) {
      expect(destino.roles.length).not.toBe(3);
    }
  });
});
