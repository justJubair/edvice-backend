import express from "express";
import { BlogRoutes } from "../modules/blogs/blogs.routes";
import { UniversityRoutes } from "../modules/university/university.routes";
import { UniversityV2Routes } from "../modules/university-v2/universityv2.routes";

const router = express.Router();

// Define module routes for the LMS API
const moduleRoutes = [
  {
    path: "/blogs",
    route: BlogRoutes,
  },
  // {
  //   path: "/universities",
  //   route: UniversityRoutes,
  // },
  {
    path: "/universities",
    route: UniversityV2Routes,
  },
];

// Dynamically register module routes
moduleRoutes.forEach((route) => {
  try {
    router.use(route.path, route.route);
  } catch (error) {
    console.error(`Failed to load route ${route.path}:`, error);
  }
});

export default router;
